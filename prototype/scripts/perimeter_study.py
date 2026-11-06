"""Compare ways of measuring perimeter (and so circularity) on shapes with a known answer.

Shapes are drawn at 16x resolution and averaged down, like a camera sensor
integrating light over each pixel, then lightly blurred. The mask is taken at
half coverage, the same rule segment.py uses for particle edges.

    python scripts/perimeter_study.py
"""
import math
import sys
from pathlib import Path

import cv2
import numpy as np
from skimage import measure as skm

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mippr.measure import perimeter_imagej  # noqa: E402

SS = 16  # supersampling factor


def render(poly_fn, size):
    """Coverage image (0-1) of a shape; poly_fn draws it on a canvas at SS x scale."""
    big = np.zeros((size * SS, size * SS), np.uint8)
    poly_fn(big)
    cov = cv2.resize(big.astype(np.float32) / 255, (size, size), interpolation=cv2.INTER_AREA)
    return cv2.GaussianBlur(cov, (0, 0), 0.8)


def disc(r, cx, cy):
    def f(img):
        cv2.circle(img, (int(cx * SS), int(cy * SS)), int(r * SS), 255, -1)
    return f, 2 * math.pi * r, math.pi * r * r


def rect(w, h, angle, cx, cy):
    pts = cv2.boxPoints(((cx * SS, cy * SS), (w * SS, h * SS), angle))
    def f(img):
        cv2.fillPoly(img, [np.round(pts).astype(np.int32)], 255)
    return f, 2 * (w + h), w * h


def blob(scale, angle, cx, cy):
    """Irregular fragment-like polygon."""
    base = np.array([[0, -1], [0.8, -0.7], [1.0, 0.1], [0.5, 0.9], [-0.3, 1.0], [-1.0, 0.3], [-0.7, -0.6]])
    a = math.radians(angle)
    R = np.array([[math.cos(a), -math.sin(a)], [math.sin(a), math.cos(a)]])
    pts = (base @ R.T) * scale + [cx, cy]
    per = float(np.sum(np.linalg.norm(np.roll(pts, -1, 0) - pts, axis=1)))
    area = 0.5 * abs(float(np.dot(pts[:, 0], np.roll(pts[:, 1], -1)) - np.dot(pts[:, 1], np.roll(pts[:, 0], -1))))
    def f(img):
        cv2.fillPoly(img, [np.round(pts * SS).astype(np.int32)], 255)
    return f, per, area


def methods(cov):
    mask = cov >= 0.5
    m8 = mask.astype(np.uint8)
    contours, _ = cv2.findContours(m8, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    c = max(contours, key=len)
    out = {}
    out["pixel_centre"] = cv2.arcLength(c, True)  # prototype v0.1 method
    out["imagej"] = perimeter_imagej(mask)
    out["crack_edge"] = _crack_length(mask)
    out["skimage_weighted"] = skm.perimeter(mask, neighborhood=8)
    # Sub-pixel outline: marching squares on the coverage (difference) image at the half level.
    iso = skm.find_contours(np.pad(cov, 1), 0.5)
    iso = max(iso, key=len)
    out["subpixel_iso"] = float(np.sum(np.linalg.norm(np.diff(iso, axis=0), axis=1)))
    area_px = mask.sum()
    return out, area_px


def _crack_length(mask):
    """Length along pixel edges (every exposed pixel side counts 1)."""
    m = np.pad(mask, 1).astype(np.int8)
    return float(np.abs(np.diff(m, axis=0)).sum() + np.abs(np.diff(m, axis=1)).sum())


def main():
    rng = np.random.default_rng(0)
    cases = []
    for r in (3.5, 5, 8, 12, 20, 30):  # 3.5 px radius = 7 px across = 500 um at ~71 um/px
        for _ in range(6):
            cases.append(("disc", r * 2, disc(r, 40 + rng.random(), 40 + rng.random())))
    for (w, h) in ((8, 8), (20, 20), (24, 6), (40, 10), (60, 4)):
        for ang in (0, 10, 22.5, 30, 45, 60, 80):
            cases.append((f"rect {w}x{h}", max(w, h), rect(w, h, ang, 40.3, 40.6)))
    for s in (5, 10, 20):
        for ang in (0, 15, 30, 45, 70):
            cases.append(("fragment", 2 * s, blob(s, ang, 40.2, 40.7)))

    names = None
    rows = []
    for kind, size, (fn, true_p, true_a) in cases:
        cov = render(fn, 80)
        meas, area_px = methods(cov)
        names = list(meas)
        true_circ = 4 * math.pi * true_a / true_p ** 2
        rows.append((kind, size, true_p, true_circ, area_px, meas))

    def summarise(sel, label):
        print(f"\n{label}  (n={len(sel)})")
        print(f"{'method':18s} {'perimeter error':>26s} {'circularity error':>28s}")
        for n in names:
            pe = np.array([r[5][n] / r[2] - 1 for r in sel])
            ce = np.array([min(1.0, 4 * math.pi * r[4] / r[5][n] ** 2) - r[3] for r in sel])
            print(f"{n:18s} median {np.median(pe):+6.1%}  worst {pe[np.argmax(abs(pe))]:+6.1%}   "
                  f"median {np.median(ce):+.3f}  worst {ce[np.argmax(abs(ce))]:+.3f}")

    summarise(rows, "ALL SHAPES")
    summarise([r for r in rows if r[1] <= 10], "SMALL (<= 10 px across, i.e. under ~0.7 mm at current resolution)")
    summarise([r for r in rows if r[1] >= 20], "LARGE (>= 20 px across)")
    summarise([r for r in rows if r[0] == "disc"], "DISCS (true circularity 1.0)")

    # Rotation sensitivity: same rectangle at different angles should give the same answer.
    print("\nROTATION: spread (max - min) of perimeter across 7 angles, as % of true")
    for kind in sorted({r[0] for r in rows if r[0].startswith("rect")}):
        sel = [r for r in rows if r[0] == kind]
        line = "  ".join(f"{n} {(max(r[5][n] for r in sel) - min(r[5][n] for r in sel)) / sel[0][2]:5.1%}"
                         for n in names)
        print(f"  {kind:10s} {line}")


if __name__ == "__main__":
    main()
