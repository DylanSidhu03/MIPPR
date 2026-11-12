"""Synthetic photos and the Python marker results, for the JS marker/rectification parity test.

Run from the repo root: .venv/bin/python web/tests/dump_python_markers.py
Writes web/tests/fixtures/photo_*.png (greyscale) and markers.json (committed).
"""
import json
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipeline"))
from mippr.capture.sheet import Layout, detect_markers, find_sheet  # noqa: E402
from mippr.capture.synthetic import photograph, sheet_bgr  # noqa: E402

OUT = Path(__file__).resolve().parent / "fixtures"
PHOTOS = [("white_grid", "letter", 5, -0.03), ("checkerboard", "a4", 6, -0.04)]
SAMPLES = 400  # rectified-sheet pixels compared per case


def blank_marker(gray, corners, pad=6):
    """Paint one marker out (white), as if it were cut off or covered."""
    x0, y0 = np.floor(corners.min(axis=0)).astype(int) - pad
    x1, y1 = np.ceil(corners.max(axis=0)).astype(int) + pad
    out = gray.copy()
    out[max(0, y0):y1, max(0, x0):x1] = 255
    return out, [int(x0), int(y0), int(x1), int(y1)]


def case(gray, blank=None):
    sh = find_sheet(gray)
    rect = sh.rectify_sheet(gray)
    rng = np.random.default_rng(0)
    ys, xs = rng.integers(0, rect.shape[0], SAMPLES), rng.integers(0, rect.shape[1], SAMPLES)
    return {
        "blank": blank,
        "markers": {str(k): v.tolist() for k, v in sorted(detect_markers(gray).items())},
        "layout": [sh.layout.background, sh.layout.paper],
        "pxPerMm": float(sh.px_per_mm),
        "markersFound": sh.markers_found,
        "homography": sh.homography.ravel().tolist(),
        "rectifiedSize": [rect.shape[1], rect.shape[0]],
        "samples": [[int(x), int(y), int(rect[y, x])] for x, y in zip(xs, ys)],
    }


cases = []
for bg, paper, seed, k1 in PHOTOS:
    gray = cv2.cvtColor(photograph(sheet_bgr(Layout(bg, paper), 300), seed=seed, k1=k1, out_width=1200),
                        cv2.COLOR_BGR2GRAY)
    name = f"photo_{bg}_{paper}.png"
    cv2.imwrite(str(OUT / name), gray, [cv2.IMWRITE_PNG_COMPRESSION, 9])
    full = case(gray)
    first = min(full["markers"], key=int)
    blanked, box = blank_marker(gray, np.array(full["markers"][first]))
    cases.append({"photo": name, **full})
    cases.append({"photo": name, **case(blanked, box)})
(OUT / "markers.json").write_text(json.dumps({"opencv": cv2.__version__, "cases": cases}) + "\n")
print(f"Wrote {len(PHOTOS)} photos and {len(cases)} cases to {OUT.relative_to(ROOT)}")
