"""Synthetic particles and the Python measurement results, for the JS measurement parity test.

Run from the repo root: .venv/bin/python web/tests/dump_python_measure.py
Writes (committed):
- web/tests/fixtures/measure_inputs.json.gz: per case, the labels, image, difference map, expected
  background and line mask (base64, row-major).
- web/tests/fixtures/measure_expected.json: measure()'s rows for each case.
- web/tests/fixtures/measure_algorithms.json: skimage skeletons and contours, SciPy longest paths,
  ImageJ perimeters and Feret values on small random inputs (for the tests that need no OpenCV.js).
"""
import base64
import gzip
import json
import math
import sys
from pathlib import Path

import cv2
import numpy as np
from skimage.measure import find_contours
from skimage.morphology import skeletonize

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipeline"))
from mippr.measurement.fiber import _longest_path, _smooth_length, fiber_metrics  # noqa: E402
from mippr.measurement.geometry import feret, measure, perimeter_imagej  # noqa: E402
from mippr.segmentation.edges import refine_edges  # noqa: E402

OUT = Path(__file__).resolve().parent / "fixtures"
WHITE, BLACK = (235, 232, 228), (32, 30, 34)
CELL = 32  # box_fn: letter per 32 px row, number per 32 px column


def b64(a):
    return base64.b64encode(np.ascontiguousarray(a).tobytes()).decode()


def background(h, w, split=None):
    bg = np.empty((h, w, 3), np.float32)
    bg[:] = WHITE
    if split is not None:
        bg[:, split:] = BLACK
    return bg


def photograph(bg, layers, sigma, seed):
    """Blend each (mask, bgr, alpha) layer over the background, blur and add a little noise."""
    img = bg.astype(np.float64)
    for mask, bgr, alpha in layers:
        img[mask] = alpha * np.array(bgr, np.float64) + (1 - alpha) * img[mask]
    if sigma > 0:
        img = cv2.GaussianBlur(img, (0, 0), sigma)
    img += np.random.default_rng(seed).normal(0, 1.5, img.shape)
    return np.clip(np.round(img), 0, 255).astype(np.uint8)


def difference(img, bg):
    p = cv2.GaussianBlur(img.astype(np.float32), (0, 0), 1.0)
    return np.abs(p - bg).max(axis=2).astype(np.float32)


def segment(diff, low=20.0):
    refined = refine_edges(diff >= low, diff, 0.5)
    n, labels = cv2.connectedComponents(refined.astype(np.uint8), connectivity=8)
    return labels.astype(np.int32)


def shape(h, w, draw):
    m = np.zeros((h, w), np.uint8)
    draw(m)
    return m.astype(bool)


def disc(cx, cy, r):
    return lambda m: cv2.circle(m, (cx, cy), r, 1, -1)


def rotated_rect(cx, cy, length, width, angle):
    pts = cv2.boxPoints(((cx, cy), (length, width), angle))
    return lambda m: cv2.fillPoly(m, [np.round(pts).astype(np.int32)], 1)


def polyline(pts, thickness):
    return lambda m: cv2.polylines(m, [np.array(pts, np.int32)], False, 1, thickness)


def arc(cx, cy, r, a0, a1, n=40):
    t = np.radians(np.linspace(a0, a1, n))
    return np.stack([cx + r * np.cos(t), cy + r * np.sin(t)], axis=1).round().astype(int).tolist()


def case(name, h, w, layers, sigma=0.8, split=None, seed=0, labels=None, use_diff=True, use_bg=True,
         line=None, color_gain=None, um_per_px=50.0, edge_margin_px=3):
    bg = background(h, w, split)
    img = photograph(bg, [(shape(h, w, d), c, a) for d, c, a in layers], sigma, seed)
    diff = difference(img, bg)
    if labels is None:
        labels = segment(diff)
    color = None
    if color_gain is not None:
        color = np.clip(img.astype(np.float32) * np.array(color_gain, np.float32), 0, 255).astype(np.uint8)
    line_mask = None
    if line is not None:
        line_mask = np.zeros((h, w), bool)
        line_mask[:, line[0]:line[1]] = True
    rows = measure(labels, img, um_per_px, diff if use_diff else None, 0.5, edge_margin_px,
                   box_fn=lambda x, y: f"{chr(65 + int(y // CELL))}{int(x // CELL) + 1}", line_mask=line_mask,
                   color_img=color, bg_img=bg if use_bg else None)
    assert labels.max() < 256
    inputs = {
        "name": name, "width": w, "height": h, "umPerPx": um_per_px, "edgeMarginPx": edge_margin_px,
        "cell": CELL, "labels": b64(labels.astype(np.uint8)), "img": b64(img),
        "diff": b64(diff) if use_diff else None, "bg": b64(bg) if use_bg else None,
        "color": b64(color) if color is not None else None,
        "line": b64(line_mask.astype(np.uint8)) if line_mask is not None else None,
    }
    return inputs, {"name": name, "rows": [clean(r) for r in rows]}


def clean(v):
    if isinstance(v, dict):
        return {k: clean(x) for k, x in v.items()}
    if isinstance(v, (bool, np.bool_)):
        return bool(v)
    if isinstance(v, (int, np.integer)):
        return int(v)
    if isinstance(v, (float, np.floating)):
        return None if math.isnan(v) else float(v)
    return v


def cases():
    blue, green, red, grey = (200, 90, 30), (40, 160, 60), (40, 40, 210), (120, 120, 120)
    yield case("discs", 64, 96, [(disc(20, 30, 10), blue, 1), (disc(60, 20, 4), red, 1), (disc(80, 48, 2), green, 1)])
    yield case("rectangles", 72, 96, [(rotated_rect(30, 34, 34, 9, 20), red, 1),
                                      (lambda m: cv2.rectangle(m, (62, 20), (75, 26), 1, -1), blue, 1),
                                      (lambda m: cv2.rectangle(m, (66, 44), (73, 51), 1, -1), green, 1)],
               seed=1, line=(48, 50))
    yield case("fiber_straight", 56, 96, [(polyline([(8, 10), (86, 44)], 3), blue, 1)], seed=2)
    yield case("fiber_curved", 80, 96, [(polyline(arc(48, 70, 40, 200, 340), 4), red, 1),
                                        (polyline([(10, 20), (30, 12), (50, 22), (70, 14)], 2), grey, 1)], seed=3)
    ring = shape(48, 48, lambda m: cv2.circle(m, (24, 24), 14, 1, -1)) & ~shape(48, 48, disc(24, 24, 6))
    yield case("hole", 48, 48, [(lambda m: m.__setitem__(ring, 1), green, 1)], seed=4, labels=ring.astype(np.int32))
    yield case("two_colour_edge", 64, 96, [(rotated_rect(48, 30, 30, 14, -10), grey, 1),
                                           (disc(18, 44, 7), (190, 200, 210), 0.35),
                                           (disc(78, 46, 7), (150, 160, 170), 1)], split=48, seed=5)
    small = np.zeros((40, 40), np.int32)
    small[10, 10] = 1
    small[20:22, 20:22] = 2
    small[30, 28:31] = 3
    small[8:13, 30] = 4
    yield case("small", 40, 40, [(lambda m: m.__setitem__(small > 0, 1), red, 1)], sigma=0.0, seed=6, labels=small)
    yield case("blurred", 64, 96, [(disc(24, 32, 9), blue, 1), (polyline([(50, 12), (88, 50)], 3), red, 1)],
               sigma=2.5, seed=7, color_gain=(1.05, 1.0, 0.92))
    labels = (shape(40, 56, disc(10, 12, 7)).astype(np.int32)
              + 2 * shape(40, 56, rotated_rect(40, 30, 20, 6, 60)).astype(np.int32))
    yield case("no_diff", 40, 56, [(lambda m: m.__setitem__(labels > 0, 1), grey, 1)], seed=8, labels=labels,
               use_diff=False, use_bg=False, edge_margin_px=4)
    yield case("light_on_dark", 56, 64, [(disc(32, 28, 9), (220, 225, 230), 1), (disc(12, 44, 4), (60, 200, 240), 0.6)],
               split=0, seed=9)


def algorithms():
    rng = np.random.default_rng(11)
    skel, contours, perims, ferets = [], [], [], []
    for k in range(12):
        h, w = int(rng.integers(8, 24)), int(rng.integers(8, 24))
        m = rng.random((h, w)) < rng.uniform(0.4, 0.8)
        if k % 2:
            m = cv2.morphologyEx(m.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8)).astype(bool)
        s = skeletonize(m)
        path = _longest_path(s)
        skel.append({"width": w, "height": h, "mask": b64(m.astype(np.uint8)), "skeleton": b64(s.astype(np.uint8)),
                     "path": path.astype(int).tolist(), "smoothLength": _smooth_length(path),
                     "fiber": [float(v) for v in fiber_metrics(m)[:2]] + [bool(fiber_metrics(m)[2])]})
        _, lab = cv2.connectedComponents(m.astype(np.uint8), connectivity=8)
        one = lab == 1 if lab.max() else m
        perims.append({"width": w, "height": h, "mask": b64(one.astype(np.uint8)), "perimeter": perimeter_imagej(one)})
    for k in range(8):
        h, w = int(rng.integers(5, 16)), int(rng.integers(5, 16))
        f = cv2.GaussianBlur(rng.random((h, w)), (0, 0), 1.0) if k % 2 else rng.random((h, w))
        f[rng.random((h, w)) < 0.1] = 0.5  # values exactly on the level (degenerate segments)
        lines = find_contours(f, 0.5)
        contours.append({"width": w, "height": h, "field": b64(f.astype(np.float64)), "level": 0.5,
                         "contours": [c.tolist() for c in lines]})
    for k in range(10):
        pts = rng.integers(0, 30, (int(rng.integers(3, 12)), 2)).astype(np.float32) + 0.5
        hull = cv2.convexHull(pts).reshape(-1, 2).astype(np.float64)
        ferets.append({"hull": hull.tolist(), "feret": list(feret(hull))})
    return {"skeletons": skel, "contours": contours, "perimeters": perims, "ferets": ferets}


if __name__ == "__main__":
    inputs, expected = zip(*cases())
    OUT.mkdir(exist_ok=True)
    with gzip.open(OUT / "measure_inputs.json.gz", "wt", compresslevel=9) as f:
        json.dump(list(inputs), f)
    (OUT / "measure_expected.json").write_text(json.dumps(list(expected), indent=1) + "\n")
    (OUT / "measure_algorithms.json").write_text(json.dumps(algorithms()) + "\n")
    for e in expected:
        print(e["name"], len(e["rows"]), "particles")
