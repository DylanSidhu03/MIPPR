"""Measure a photo of the lab's old 12 x 24 checkerboard with the pipeline (validation only).

The app only takes photos on the three printed MIPPR backgrounds. This runs the same
measurement, colour and shape code on the lab's earlier setup (a particle photo plus
an empty-board photo), so its numbers can be compared with the lab's ImageJ results
(validation/compare_imagej.py, results in validation/results/fragment_area_sample/).

    python validation/legacy/run.py particle.jpg template.jpg --square-mm 10 --sample-id FA01 --out OUT
"""
import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

import cv2

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "pipeline"))
sys.path.insert(0, str(HERE.parent))

from mippr import __version__  # noqa: E402
from mippr.cli import _write, draw_overlay, image_id, picture_label  # noqa: E402
from mippr.export import METADATA, build_rows  # noqa: E402
from mippr.measurement.geometry import measure  # noqa: E402

from legacy.board import find_board  # noqa: E402
from legacy.segment import SegmentParams, grid_band, segment, well_id  # noqa: E402


def measure_board(rect_p, rect_t, px_per_square, um_per_px, params=SegmentParams()):
    """Segment and measure a rectified particle photo against its rectified empty board."""
    labels, diff = segment(rect_p, rect_t, px_per_square, params)
    measured = measure(labels, rect_p, um_per_px, diff, params.edge_fraction, params.edge_margin_px,
                       box_fn=lambda x, y: well_id(x, y, px_per_square),
                       line_mask=grid_band(labels.shape, px_per_square, 0),
                       bg_img=rect_t)  # the empty-board photo is the background behind every pixel
    return labels, diff, measured


def run_legacy(particle_path, template_path, square_mm, out_dir, sample_id="sample", photo=1, metadata=None,
               px_per_square=140, params=SegmentParams()):
    particle = cv2.imread(str(particle_path))
    template = cv2.imread(str(template_path))
    if particle is None or template is None:
        raise ValueError("Could not read one of the images.")
    rect_p = find_board(particle, px_per_square).rectify(particle)
    rect_t = find_board(template, px_per_square).rectify(template)
    um_per_px = square_mm * 1000 / px_per_square
    labels, diff, measured = measure_board(rect_p, rect_t, px_per_square, um_per_px, params)
    label = picture_label(sample_id, photo)
    rows = build_rows(measured, sample_id, label, image_id(particle_path), metadata or {}, __version__,
                      um_per_px / 1000, datetime.now(timezone.utc).isoformat(timespec="seconds"),
                      background_type="legacy_checkerboard", scale_source="legacy_board")
    _write(out_dir, rows, draw_overlay(rect_p, labels, measured, rows), {
        "mode": "legacy (validation only)", "particle": str(particle_path), "template": str(template_path),
        "sample_id": sample_id, "picture_label": label, **(metadata or {}),
        "square_mm": square_mm, "px_per_square": px_per_square, "mm_per_px": um_per_px / 1000,
        "params": vars(params)})
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("particle")
    ap.add_argument("template")
    ap.add_argument("--square-mm", type=float, required=True, help="side of one printed square in mm")
    ap.add_argument("--px-per-square", type=int, default=140)
    ap.add_argument("--out", default="out")
    ap.add_argument("--sample-id", default="sample")
    ap.add_argument("--photo", type=int, default=1)
    for k in METADATA:
        ap.add_argument(f"--{k}", default="")
    a = ap.parse_args()
    rows = run_legacy(a.particle, a.template, a.square_mm, a.out, a.sample_id, a.photo,
                      {k: getattr(a, k) for k in METADATA}, a.px_per_square)
    print(f"{len(rows)} particles -> {a.out}/particles.csv")


if __name__ == "__main__":
    main()
