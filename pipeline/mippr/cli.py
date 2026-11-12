"""Command line for the MIPPR pipeline.

    # Printable backgrounds (Drive spec v0.6): PNG + PDF, print at actual size
    python -m mippr.cli sheet --background white_grid --paper letter --out ../backgrounds/

    # A photo of particles on a printed sheet, one particle per box
    python -m mippr.cli grid photo.jpg --sample-id S042 --photo 1 --out results/

    # The lab's existing photos: particle photo + empty-board photo of the 12 x 24 checkerboard
    python -m mippr.cli legacy particle.jpg template.jpg --square-mm 10 --sample-id S042 --out results/

`grid` and `legacy` write particles.csv (one row per particle) and
summary.csv (one row per sample), both as defined in docs/OUTPUT_CSV.md, plus
overlay.png (outlines and particle IDs), run.json (settings and versions) and
NOTE.txt.
"""
import argparse
import csv
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np

from . import __version__
from .capture.board import find_board
from .capture.calibration import check_quality, measure_quality, white_balance
from .capture.sheet import BACKGROUNDS, PAPERS, Layout, find_sheet, save_sheet
from .export import COLUMNS, METADATA, NOTE, SUMMARY_COLUMNS, build_rows, build_summary
from .measurement.geometry import measure
from .segmentation.grid import GridSegmentParams, background_image, box_of, line_band, segment_grid
from .segmentation.legacy import SegmentParams, segment


def draw_overlay(img, labels, measured, rows):
    out = img.copy()
    for m, r in zip(measured, rows):
        mask = (labels == m["particle"]).astype("uint8")
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        cv2.drawContours(out, contours, -1, (0, 0, 255), 1)
        x, y, w, h = cv2.boundingRect(contours[0])
        for color, thick in (((255, 255, 255), 3), ((0, 0, 200), 1)):
            cv2.putText(out, str(r["particle_id"]), (x + w + 3, y + h // 2 + 5), cv2.FONT_HERSHEY_SIMPLEX,
                        0.5, color, thick, cv2.LINE_AA)
    return out


def image_id(path):
    """File name plus a short hash of the file, so two photos with the same name stay distinct."""
    digest = hashlib.sha1(Path(path).read_bytes()).hexdigest()[:8]
    return f"{Path(path).stem}-{digest}"


def picture_label(sample_id, photo):
    return f"{sample_id}-P{int(photo):02d}"


def _write(out_dir, rows, overlay, run_info):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, cols, data in (("particles.csv", COLUMNS, rows), ("summary.csv", SUMMARY_COLUMNS, build_summary(rows))):
        with open(out_dir / name, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            w.writerows(data)
    cv2.imwrite(str(out_dir / "overlay.png"), overlay)
    (out_dir / "NOTE.txt").write_text(NOTE + "\n")
    (out_dir / "run.json").write_text(json.dumps({"mippr_version": __version__, **run_info,
                                                  "particles": len(rows), "note": NOTE}, indent=2))


def run_grid(photo_path, out_dir, sample_id="sample", photo=1, metadata=None, line_mm=None,
             params=GridSegmentParams()):
    img = cv2.imread(str(photo_path))
    if img is None:
        raise ValueError("Could not read the photo.")
    try:
        sheet = find_sheet(img)
    except ValueError as e:  # can't go on without the sheet; say what else is wrong with the photo
        problems = check_quality(img)
        raise ValueError("\n".join([str(e)] + [f"photo check: {p.message}" for p in problems
                                                if p.code not in ("no_markers", "marker_missing")])) from e
    # Photo quality check: warn, but measure anyway (the problems go into run.json).
    quality = measure_quality(img, sheet)
    problems = check_quality(img, sheet, metrics=quality)
    for p in problems:
        print(f"warning: {p.message}", file=sys.stderr)
    lay, ppm = sheet.layout, sheet.px_per_mm
    rect = sheet.rectify_grid(img)
    gains, wb = white_balance(sheet, img)
    balanced = np.clip(rect.astype(np.float32) * gains, 0, 255).astype(np.uint8)
    labels, diff, _ = segment_grid(rect, lay, ppm, params)
    # A particle "touches a line" if it reaches the masked band round a printed line
    # (the line plus its margin); the outer border band also means it may be cut off.
    band, _, outer = line_band(lay, ppm, labels.shape, params.line_margin_mm)
    near_line = cv2.dilate(band.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)
    mm_per_px = 1.0 / ppm
    corrected = line_mm is not None and abs(line_mm - 100.0) > 1e-9
    if corrected:  # the printer scaled the sheet: every printed length is off by the same factor
        mm_per_px *= line_mm / 100.0
    # flag_edge: within the masked border band of the grid's outer edge, so possibly cut off
    measured = measure(labels, rect, mm_per_px * 1000, None, diff, params.edge_fraction,
                       edge_margin_px=int(np.ceil(outer)) + 2,
                       box_fn=lambda x, y: lay.box_label(*box_of(lay, ppm, x, y)), line_mask=near_line,
                       color_img=balanced, bg_img=background_image(balanced, lay, ppm, params.inset_frac))
    label = picture_label(sample_id, photo)
    rows = build_rows(measured, sample_id, label, image_id(photo_path), metadata or {}, __version__, mm_per_px,
                      datetime.now(timezone.utc).isoformat(timespec="seconds"),
                      background_type=lay.background,
                      scale_source="user_corrected" if corrected else "markers",
                      scale_flag=corrected or sheet.markers_found < 4, merged_area_rule=False)
    _write(out_dir, rows, draw_overlay(balanced, labels, measured, rows), {
        "mode": "grid", "photo": str(photo_path), "sample_id": sample_id, "picture_label": label,
        **(metadata or {}), "background_type": lay.background, "paper": lay.paper,
        "layout": {"box_mm": lay.box_mm, "line_mm": lay.line_mm, "rows": lay.rows, "cols": lay.cols},
        "markers_found": sheet.markers_found, "px_per_mm": ppm, "mm_per_px": mm_per_px,
        "printed_line_mm": line_mm, "white_balance": wb,
        "quality": {"problems": [p.as_dict() for p in problems], "metrics": quality}, "params": vars(params)})
    return rows


def run_legacy(particle_path, template_path, square_mm, out_dir, sample_id="sample", photo=1, metadata=None,
               px_per_square=140, params=SegmentParams()):
    particle = cv2.imread(str(particle_path))
    template = cv2.imread(str(template_path))
    if particle is None or template is None:
        raise ValueError("Could not read one of the images.")
    rect_p = find_board(particle, px_per_square).rectify(particle)
    rect_t = find_board(template, px_per_square).rectify(template)
    labels, diff = segment(rect_p, rect_t, px_per_square, params)
    um_per_px = square_mm * 1000 / px_per_square
    # The empty-board photo is the background behind every pixel (for opacity).
    measured = measure(labels, rect_p, um_per_px, px_per_square, diff, params.edge_fraction,
                       params.edge_margin_px, bg_img=rect_t)
    label = picture_label(sample_id, photo)
    rows = build_rows(measured, sample_id, label, image_id(particle_path), metadata or {}, __version__,
                      um_per_px / 1000, datetime.now(timezone.utc).isoformat(timespec="seconds"))
    _write(out_dir, rows, draw_overlay(rect_p, labels, measured, rows), {
        "mode": "legacy", "particle": str(particle_path), "template": str(template_path),
        "sample_id": sample_id, "picture_label": label, **(metadata or {}),
        "square_mm": square_mm, "px_per_square": px_per_square, "mm_per_px": um_per_px / 1000,
        "params": vars(params)})
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("sheet", help="make a printable background (vector PDF; --png also writes an image)")
    s.add_argument("--background", choices=BACKGROUNDS, default="white_grid")
    s.add_argument("--paper", choices=tuple(PAPERS), default="letter")
    s.add_argument("--png", action="store_true", help="also write a PNG at --dpi")
    s.add_argument("--dpi", type=int, default=600)
    s.add_argument("--out", default="sheets")

    def common(p):
        p.add_argument("--out", default="out", help="output folder")
        p.add_argument("--sample-id", default="sample", help="sample ID (e.g. S042)")
        p.add_argument("--photo", type=int, default=1, help="photo number within the sample (picture label P01, P02 ...)")
        for k in METADATA:
            p.add_argument(f"--{k}", default="", help=f"{k} recorded in every row")

    g = sub.add_parser("grid", help="measure a photo of a printed grid sheet")
    g.add_argument("image", help="photo of particles on a printed MIPPR sheet")
    g.add_argument("--line-mm", type=float, help="measured length of the printed 100 mm line, if it isn't 100 mm")
    common(g)

    lg = sub.add_parser("legacy", help="the lab's 12 x 24 checkerboard: particle photo + empty-board photo")
    lg.add_argument("particle")
    lg.add_argument("template")
    lg.add_argument("--square-mm", type=float, required=True,
                    help="side of one printed checkerboard square in mm (measure it with a ruler)")
    lg.add_argument("--px-per-square", type=int, default=140)
    common(lg)

    a = ap.parse_args(argv)
    try:
        if a.cmd == "sheet":
            out = Path(a.out)
            out.mkdir(parents=True, exist_ok=True)
            lay = Layout(a.background, a.paper)
            stem = out / f"mippr_{a.background}_{a.paper}"
            save_sheet(lay, f"{stem}.png" if a.png else None, f"{stem}.pdf", a.dpi)
            print(f"{lay.rows} x {lay.cols} boxes of {lay.box_mm:g} mm -> {stem}.pdf (print at actual size)")
            return
        meta = {k: getattr(a, k) for k in METADATA}
        if a.cmd == "grid":
            rows = run_grid(a.image, a.out, a.sample_id, a.photo, meta, a.line_mm)
        else:
            rows = run_legacy(a.particle, a.template, a.square_mm, a.out, a.sample_id, a.photo, meta,
                              a.px_per_square)
    except ValueError as e:
        sys.exit(f"error: {e}")
    flagged = sum(bool(r["review_reason"]) for r in rows)
    print(f"{len(rows)} particles ({flagged} flagged for review) -> {a.out}/particles.csv, {a.out}/overlay.png")


if __name__ == "__main__":
    main()
