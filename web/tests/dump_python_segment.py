"""Rectified grid images and Python's segment_grid results, for the JS segmentation parity test.

Run from the repo root: .venv/bin/python web/tests/dump_python_segment.py
The synthetic photos use the particles of pipeline/tests/test_grid.py plus two blobs in H4 and a
disc cut by the grid's outer edge in A1. They are flattened with Python (sheet.rectify_grid), so
the JS test doesn't depend on the JS flattening. Noise-free photos at full size keep the colour
PNGs small; one smaller noisy photo checks thresholds on a noisy difference map.
Writes web/tests/fixtures/segment_<case>_{grid,labels,diff,band}.png and segment.json (committed).
"""
import json
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipeline"))
sys.path.insert(0, str(ROOT / "pipeline" / "tests"))
from mippr.capture.sheet import Layout, find_sheet  # noqa: E402
from mippr.capture.synthetic import draw_particle, photograph, sheet_bgr  # noqa: E402
from mippr.segmentation.grid import GridSegmentParams, box_of, segment_grid  # noqa: E402
from test_grid import DPI, PARTICLES  # noqa: E402

OUT = Path(__file__).resolve().parent / "fixtures"
EXTRA = [("H4", "disc", 1.2, (200, 200, 60), (-2.5, 0), {}), ("H4", "disc", 1.2, (200, 200, 60), (2.5, 0), {}),
         ("A1", "disc", 2.0, (60, 200, 230), (-5.5, 0), {})]
# (case name, background, paper, seed, out_width, noise)
CASES = [("white_grid", "white_grid", "letter", 2, 2400, 0.0),
         ("black_grid", "black_grid", "letter", 3, 2400, 0.0),
         ("checkerboard", "checkerboard", "letter", 2, 2400, 0.0),
         ("checkerboard_noisy", "checkerboard", "a4", 5, 1400, 2.0)]
SAMPLES = 2000  # exact difference values compared per case
PNG = [cv2.IMWRITE_PNG_COMPRESSION, 9]


def scene(lay, seed, out_width, noise):
    img = sheet_bgr(lay, DPI)
    for box, shape, size, col, off, kw in list(PARTICLES) + EXTRA:
        draw_particle(img, lay, DPI, box, shape, size, col, offset_mm=off, **kw)
    return photograph(img, seed=seed, k1=-0.03, out_width=out_width, noise=noise)


cases = []
for name, bg, paper, seed, width, noise in CASES:
    lay = Layout(bg, paper)
    photo = scene(lay, seed, width, noise)
    sh = find_sheet(photo)
    rect = sh.rectify_grid(photo)
    labels, diff, band = segment_grid(rect, lay, sh.px_per_mm)
    assert labels.max() < 256
    files = {k: f"segment_{name}_{k}.png" for k in ("grid", "labels", "diff", "band")}
    cv2.imwrite(str(OUT / files["grid"]), rect, PNG)
    cv2.imwrite(str(OUT / files["labels"]), labels.astype(np.uint8), PNG)
    cv2.imwrite(str(OUT / files["diff"]), np.clip(np.round(diff), 0, 255).astype(np.uint8), PNG)
    cv2.imwrite(str(OUT / files["band"]), band.astype(np.uint8) * 255, PNG)
    particles = []
    for k in range(1, labels.max() + 1):
        ys, xs = np.nonzero(labels == k)
        particles.append({"label": k, "box": lay.box_label(*box_of(lay, sh.px_per_mm, xs.mean(), ys.mean())),
                          "area": int(len(xs)), "touchesBand": bool(band[ys, xs].any())})
    rng = np.random.default_rng(0)
    ys, xs = rng.integers(0, diff.shape[0], SAMPLES), rng.integers(0, diff.shape[1], SAMPLES)
    cases.append({"name": name, "layout": [bg, paper], "pxPerMm": float(sh.px_per_mm),
                  "size": [rect.shape[1], rect.shape[0]], **files, "particles": particles,
                  "diffSamples": [[int(x), int(y), float(diff[y, x])] for x, y in zip(xs, ys)]})
    print(name, [p["box"] for p in particles])
(OUT / "segment.json").write_text(json.dumps({"opencv": cv2.__version__, "params": vars(GridSegmentParams()),
                                              "cases": cases}) + "\n")
print(f"Wrote {len(cases)} cases to {OUT.relative_to(ROOT)}")
