"""Command line: measure particles in one photo against its empty-template photo.

    python -m mippr.cli particle.jpg template.jpg --square-mm 10 --sample-id S042 --out results/

Writes particles.csv (one row per particle, columns as in
docs/CLASSIFICATION_SPEC.md), overlay.png (outlines and numbers on the
rectified photo), run.json (settings and versions) and NOTE.txt to the output
folder.
"""
import argparse
import csv
import json
import sys
from pathlib import Path

import cv2

from . import __version__
from .board import find_board
from .export import COLUMNS, METADATA, NOTE, build_rows
from .measure import measure
from .segment import SegmentParams, segment


def draw_overlay(img, labels, rows):
    out = img.copy()
    for r in rows:
        mask = (labels == r["particle"]).astype("uint8")
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        cv2.drawContours(out, contours, -1, (0, 0, 255), 1)
        x, y, w, h = cv2.boundingRect(contours[0])
        cv2.putText(out, str(r["particle"]), (x + w + 3, y + h // 2 + 5), cv2.FONT_HERSHEY_SIMPLEX,
                    0.5, (255, 255, 255), 3, cv2.LINE_AA)
        cv2.putText(out, str(r["particle"]), (x + w + 3, y + h // 2 + 5), cv2.FONT_HERSHEY_SIMPLEX,
                    0.5, (0, 0, 200), 1, cv2.LINE_AA)
    return out


def run(particle_path, template_path, square_mm, out_dir, sample_id="sample", metadata=None,
        px_per_square=140, params=SegmentParams()):
    particle = cv2.imread(str(particle_path))
    template = cv2.imread(str(template_path))
    if particle is None or template is None:
        raise ValueError("Could not read one of the images.")
    rect_p = find_board(particle, px_per_square).rectify(particle)
    rect_t = find_board(template, px_per_square).rectify(template)
    labels, diff = segment(rect_p, rect_t, px_per_square, params)
    um_per_px = square_mm * 1000 / px_per_square
    measured = measure(labels, rect_p, um_per_px, px_per_square, diff, params.edge_fraction)
    rows = build_rows(measured, sample_id, Path(particle_path).name, metadata or {}, __version__,
                      square_mm, um_per_px)

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "particles.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(rows)
    cv2.imwrite(str(out_dir / "overlay.png"), draw_overlay(rect_p, labels, measured))
    (out_dir / "NOTE.txt").write_text(NOTE + "\n")
    (out_dir / "run.json").write_text(json.dumps({
        "mippr_version": __version__, "particle": str(particle_path), "template": str(template_path),
        "sample_id": sample_id, **(metadata or {}),
        "square_mm": square_mm, "px_per_square": px_per_square, "um_per_px": um_per_px,
        "params": vars(params), "particles": len(rows), "note": NOTE}, indent=2))
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("particle", help="photo of the board with particles")
    ap.add_argument("template", help="photo of the same board, empty")
    ap.add_argument("--square-mm", type=float, required=True,
                    help="side of one printed checkerboard square in mm (measure it with a ruler)")
    ap.add_argument("--out", default="out", help="output folder")
    ap.add_argument("--sample-id", default="sample", help="sample ID, used in particle IDs (e.g. S042)")
    for k in METADATA:
        ap.add_argument(f"--{k}", default="", help=f"{k} recorded in every row")
    ap.add_argument("--px-per-square", type=int, default=140,
                    help="resolution of the rectified board; about the photo's own resolution is best")
    a = ap.parse_args(argv)
    try:
        rows = run(a.particle, a.template, a.square_mm, a.out, a.sample_id,
                   {k: getattr(a, k) for k in METADATA}, a.px_per_square)
    except ValueError as e:
        sys.exit(f"error: {e}")
    flagged = sum(r["review"] == "yes" for r in rows)
    print(f"{len(rows)} particles ({flagged} flagged for review) -> {a.out}/particles.csv, {a.out}/overlay.png")


if __name__ == "__main__":
    main()
