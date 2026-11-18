"""The Python grid-crossing refinement and grid rectification, for the JS rectifyGrid parity test.

Run from the repo root, after dump_python_markers.py and dump_python_quality.py (it reads their photos):
    .venv/bin/python web/tests/dump_python_rectify.py
Writes web/tests/fixtures/rectify.json (committed).

Writes rectify_checkerboard_a4.png too (greyscale, no sensor noise so it stays small).

Cases: the two greyscale marker photos (white grid Letter k1 = -0.03, checkerboard A4 k1 = -0.04,
1200 px wide), a 1600 px checkerboard A4 photo (k1 = -0.04) and the three colour quality photos
(every background, Letter, k1 = -0.03, 2400 px wide).

`unconverged` counts checkerboard corners where cv2.cornerSubPix ran all 60 iterations without
converging: its end point then depends on float rounding (it differs with and without Intel IPP),
so those photos can't be matched exactly.
"""
import json
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipeline"))
from mippr.capture.sheet import Layout, find_sheet  # noqa: E402
from mippr.capture.synthetic import photograph, sheet_bgr  # noqa: E402

OUT = Path(__file__).resolve().parent / "fixtures"
PHOTOS = ["photo_white_grid_letter.png", "photo_checkerboard_a4.png", "rectify_checkerboard_a4.png",
          "quality_white_grid.png", "quality_black_grid.png", "quality_checkerboard.png"]
SAMPLES = 600  # rectified-grid pixels compared per case

_corner_sub_pix = cv2.cornerSubPix
unconverged = 0


def counting_corner_sub_pix(img, corners, win, zero_zone, criteria):
    """cv2.cornerSubPix, counting corners that change between 59 and 60 iterations (not converged)."""
    global unconverged
    out = _corner_sub_pix(img, corners.copy(), win, zero_zone, criteria)
    one_less = _corner_sub_pix(img, corners.copy(), win, zero_zone, (criteria[0], criteria[1] - 1, criteria[2]))
    unconverged += int((np.abs(out - one_less).reshape(-1, 2).max(axis=1) > 0).sum())
    return out


cv2.cornerSubPix = counting_corner_sub_pix
gray = cv2.cvtColor(photograph(sheet_bgr(Layout("checkerboard", "a4"), 300), seed=8, k1=-0.04, out_width=1600,
                               noise=0.0), cv2.COLOR_BGR2GRAY)
cv2.imwrite(str(OUT / "rectify_checkerboard_a4.png"), gray, [cv2.IMWRITE_PNG_COMPRESSION, 9])


cases = []
for name in PHOTOS:
    img = cv2.imread(str(OUT / name), cv2.IMREAD_UNCHANGED)
    unconverged = 0
    sh = find_sheet(img)
    grid = sh.rectify_grid(img)
    rng = np.random.default_rng(1)
    ys, xs = rng.integers(0, grid.shape[0], SAMPLES), rng.integers(0, grid.shape[1], SAMPLES)
    cases.append({
        "photo": name,
        "layout": [sh.layout.background, sh.layout.paper],
        "pxPerMm": float(sh.px_per_mm),
        "homography": sh.homography.ravel().tolist(),
        "crossings": sh.crossings.tolist(),
        "residualMm": sh.residual_mm(),
        "unconverged": unconverged,
        "gridSize": [grid.shape[1], grid.shape[0]],
        "samples": [[int(x), int(y), np.atleast_1d(grid[y, x]).tolist()] for x, y in zip(xs, ys)],
    })
    print(name, sh.layout.background, sh.layout.paper, sh.px_per_mm, grid.shape, f"{sh.residual_mm():.3f} mm",
          f"unconverged {unconverged}")
(OUT / "rectify.json").write_text(json.dumps({"opencv": cv2.__version__, "cases": cases}) + "\n")
print(f"Wrote {len(cases)} cases to {(OUT / 'rectify.json').relative_to(ROOT)}")
