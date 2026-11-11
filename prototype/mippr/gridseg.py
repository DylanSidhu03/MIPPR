"""Per-box segmentation on the printed grid backgrounds (Drive spec v0.6).

After `grid.find_sheet(...).rectify_grid(photo)` the grid is flat and its
geometry is known from the printed design, so no empty-board photo is
needed:

1. Each box's background color is the median of its inside (a particle
   covers only a small part of a box).
2. The difference from that color is computed box by box. On the
   checkerboard, each half of a particle lying across a black/white edge is
   compared with its own box, which avoids the two-pass threshold the ImageJ
   macro needs.
3. Along the printed lines (and the checkerboard's box edges) the difference
   is bridged from both sides, so a line itself never becomes a particle but
   a fiber crossing it stays in one piece.
4. Hysteresis threshold, half-maximum edge placement and hole filling are
   shared with the template-difference prototype (segment.py).

Everything here exists in OpenCV.js.
"""
from dataclasses import dataclass

import cv2
import numpy as np

from .segment import _fill_holes, _hysteresis, _refine_edges


@dataclass
class GridSegmentParams:
    blur_sigma: float = 1.0
    high: float = 60.0
    low: float = 25.0
    min_area_px: int = 9
    line_margin_mm: float = 0.25  # added to each side of a printed line (blur, print spread)
    edge_fraction: float = 0.5
    inset_frac: float = 0.15  # box border left out when estimating its background color


def line_band(layout, px_per_mm, shape, margin_mm):
    """True on the printed lines (or checkerboard edges) plus a margin."""
    b = layout.box_mm * px_per_mm
    # The checkerboard has no printed lines inside, but its box edges blur just as much,
    # and its outer frame is a printed line.
    half = (layout.line_mm / 2 + margin_mm) * px_per_mm
    half = max(1.0, half)
    # The outer border is twice as wide: on the checkerboard and the black grid its
    # crossings can't be seen and come from the fitted surface, so they can be ~1 px off.
    outer = half + margin_mm * px_per_mm
    h, w = shape
    band = np.zeros(shape, bool)
    for c in range(layout.cols + 1):
        x, hw = c * b, (outer if c in (0, layout.cols) else half)
        band[:, max(0, int(np.floor(x - hw))):min(w, int(np.ceil(x + hw)) + 1)] = True
    for r in range(layout.rows + 1):
        y, hw = r * b, (outer if r in (0, layout.rows) else half)
        band[max(0, int(np.floor(y - hw))):min(h, int(np.ceil(y + hw)) + 1), :] = True
    return band, half, outer


def label_zones(layout, px_per_mm, shape):
    """True in each box's top-left label corner (empty mask when the sheet has no box labels)."""
    zones = np.zeros(shape, bool)
    if not layout.box_labels:
        return zones
    b = layout.box_mm * px_per_mm
    zw, zh = (v * px_per_mm for v in layout.label_zone_mm)
    for r in range(layout.rows):
        for c in range(layout.cols):
            x0, y0 = int(c * b), int(r * b)
            zones[y0:int(y0 + zh), x0:int(x0 + zw)] = True
    return zones


def box_of(layout, px_per_mm, x, y):
    """(row, col) of the box containing point (x, y) of the rectified grid, clipped to the grid."""
    b = layout.box_mm * px_per_mm
    return (min(layout.rows - 1, max(0, int(y // b))), min(layout.cols - 1, max(0, int(x // b))))


def background_colors(img, layout, px_per_mm, inset_frac=0.15):
    """(rows, cols, 3) median color of each box's inside."""
    b = layout.box_mm * px_per_mm
    out = np.zeros((layout.rows, layout.cols, img.shape[2]), np.float32)
    for r in range(layout.rows):
        for c in range(layout.cols):
            y0, y1 = int(r * b + inset_frac * b), int((r + 1) * b - inset_frac * b)
            x0, x1 = int(c * b + inset_frac * b), int((c + 1) * b - inset_frac * b)
            out[r, c] = np.median(img[y0:y1, x0:x1].reshape(-1, img.shape[2]), axis=0)
    return out


def background_image(img, layout, px_per_mm, inset_frac=0.15):
    """The background colour expected behind every pixel: each box's median colour, filled across the box."""
    b = layout.box_mm * px_per_mm
    h, w = img.shape[:2]
    bg = background_colors(img, layout, px_per_mm, inset_frac)
    rows = np.minimum((np.arange(h) // b).astype(int), layout.rows - 1)
    cols = np.minimum((np.arange(w) // b).astype(int), layout.cols - 1)
    return bg[rows[:, None], cols[None, :]]


def difference(img, layout, px_per_mm, params=GridSegmentParams()):
    """Largest color-channel difference from the pixel's own box background, bridged across lines."""
    b = layout.box_mm * px_per_mm
    h, w = img.shape[:2]
    bg_img = background_image(img, layout, px_per_mm, params.inset_frac)
    p = cv2.GaussianBlur(img.astype(np.float32), (0, 0), params.blur_sigma)
    d = np.abs(p - bg_img).max(axis=2)
    band, half, outer = line_band(layout, px_per_mm, (h, w), params.line_margin_mm)
    d = _bridge(d, layout, b, half, outer)
    # The printed box label in each corner is masked like the lines: no detection
    # starts there, and a particle reaching into it is bridged from below and the right.
    zones = label_zones(layout, px_per_mm, (h, w))
    if zones.any():
        d = _bridge_labels(d, layout, b, px_per_mm)
        band = band | zones
    return d, band


def _bridge_labels(d, layout, b, px_per_mm):
    d = d.copy()
    h, w = d.shape
    zw, zh = (int(np.ceil(v * px_per_mm)) for v in layout.label_zone_mm)
    for r in range(layout.rows):
        for c in range(layout.cols):
            x0, y0 = int(c * b), int(r * b)
            x1, y1 = min(w - 1, x0 + zw), min(h - 1, y0 + zh)
            below = d[y1, x0:x1][None, :]
            right = d[y0:y1, x1][:, None]
            d[y0:y1, x0:x1] = np.minimum(below, right)
    return d


def _bridge(d, layout, b, half, outer):
    """Inside each line band, use the smaller of the values just outside it on either side."""
    d = d.copy()
    h, w = d.shape
    for c in range(layout.cols + 1):
        k = int(np.ceil(outer if c in (0, layout.cols) else half)) + 1
        x = int(round(c * b))
        lo, hi = max(0, x - k + 1), min(w, x + k)
        left, right = d[:, max(0, x - k)], d[:, min(w - 1, x + k)]
        if c == 0:
            left = right * 0  # outside the grid counts as background
        if c == layout.cols:
            right = left * 0
        d[:, lo:hi] = np.minimum(left, right)[:, None]
    for r in range(layout.rows + 1):
        k = int(np.ceil(outer if r in (0, layout.rows) else half)) + 1
        y = int(round(r * b))
        lo, hi = max(0, y - k + 1), min(h, y + k)
        top, bot = d[max(0, y - k), :], d[min(h - 1, y + k), :]
        if r == 0:
            top = bot * 0
        if r == layout.rows:
            bot = top * 0
        d[lo:hi, :] = np.minimum(top, bot)[None, :]
    return d


def segment_grid(img, layout, px_per_mm, params=GridSegmentParams()):
    """Return (labels, diff, band): int32 labels (0 = background), the difference map and the line band."""
    diff, band = difference(img, layout, px_per_mm, params)
    mask = _fill_holes(_hysteresis(diff, params.low, params.high, band))
    if params.edge_fraction:
        mask = _refine_edges(mask, diff, params.edge_fraction)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=8)
    out = np.zeros_like(labels)
    k = 0
    for lbl in range(1, n):
        if stats[lbl, cv2.CC_STAT_AREA] < params.min_area_px:
            continue
        k += 1
        out[labels == lbl] = k
    return out, diff, band
