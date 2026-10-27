"""Find particles by comparing a rectified particle photo to its empty template.

Both photos must already be rectified with ``board.find_board(...).rectify``
so their squares line up pixel for pixel. Everything here uses operations
that exist in OpenCV.js (blur, absdiff, threshold, morphology, connected
components) so the browser app can port it directly.
"""
from dataclasses import dataclass

import cv2
import numpy as np

from .board import SQUARES_X, SQUARES_Y


@dataclass
class SegmentParams:
    blur_sigma: float = 1.0  # px; smooths sensor noise and sub-pixel misalignment
    high: float = 60.0  # difference (0-255) that surely marks a particle
    low: float = 25.0  # difference that may extend a particle found with `high`
    min_area_px: int = 9  # drop specks smaller than this (about 3 x 3 px)
    grid_band_px: int = 2  # half-width of the strip along each gridline treated with suspicion
    edge_margin_px: int = 3  # drop blobs touching the board edge (frame, tape, shadows)
    edge_fraction: float = 0.5  # edge sits where the difference falls to this share of the particle's contrast


def match_template_brightness(particle, template, px_per_square, inset=0.2):
    """Shift the template's brightness square by square to match the particle photo.

    The two photos are rarely exposed the same (blacks were 3x brighter in the
    lab sample). Using the median of each square's centre ignores the few
    particle pixels in it and also follows uneven lighting across the board.
    """
    p = particle.astype(np.float32)
    t = template.astype(np.float32)
    out = t.copy()
    m = int(px_per_square * inset)
    for j in range(SQUARES_Y):
        for i in range(SQUARES_X):
            y0, x0 = j * px_per_square, i * px_per_square
            y1, x1 = y0 + px_per_square, x0 + px_per_square
            pc = p[y0 + m:y1 - m, x0 + m:x1 - m].reshape(-1, p.shape[2])
            tc = t[y0 + m:y1 - m, x0 + m:x1 - m].reshape(-1, t.shape[2])
            out[y0:y1, x0:x1] += np.median(pc, axis=0) - np.median(tc, axis=0)
    return out


def difference(particle, template, px_per_square, blur_sigma=1.0, bridge_px=3):
    """Per-pixel difference (largest over the three colour channels)."""
    t = match_template_brightness(particle, template, px_per_square)
    p = cv2.GaussianBlur(particle.astype(np.float32), (0, 0), blur_sigma)
    t = cv2.GaussianBlur(t, (0, 0), blur_sigma)
    d = np.abs(p - t).max(axis=2)
    return _bridge_gridlines(d, px_per_square, bridge_px) if bridge_px else d


def _bridge_gridlines(d, px_per_square, half_width):
    """Fill dips in the difference where a particle crosses a printed square edge.

    On a square edge the template is a blurred mid-grey, so a mid-tone particle
    lying across it barely differs from the template there and gets cut in two.
    Inside a narrow strip along each edge, the difference is raised to the
    smaller of the values just outside the strip on either side: a particle
    that continues across the line is bridged, empty board stays empty.
    """
    d = d.copy()
    h, w = d.shape
    k = half_width + 1
    for i in range(1, SQUARES_X):
        x = i * px_per_square
        across = np.minimum(d[:, x - k], d[:, x + k])[:, None]
        d[:, x - half_width:x + half_width + 1] = np.maximum(d[:, x - half_width:x + half_width + 1], across)
    for j in range(1, SQUARES_Y):
        y = j * px_per_square
        across = np.minimum(d[y - k, :], d[y + k, :])[None, :]
        d[y - half_width:y + half_width + 1, :] = np.maximum(d[y - half_width:y + half_width + 1, :], across)
    return d


def grid_band(shape, px_per_square, half_width):
    """True within `half_width` px of a printed gridline (square edge)."""
    band = np.zeros(shape, bool)
    for k in range(SQUARES_X + 1):
        x = k * px_per_square
        band[:, max(0, x - half_width):x + half_width + 1] = True
    for k in range(SQUARES_Y + 1):
        y = k * px_per_square
        band[max(0, y - half_width):y + half_width + 1, :] = True
    return band


def _hysteresis(diff, low, high, band):
    """Keep low-threshold regions that contain at least one high-threshold pixel.

    Square edges never line up perfectly between the two photos, and lens colour
    fringing makes them worse, so the difference image has thin lines along the
    grid. Inside the gridline band only structures at least 3 px wide count,
    and a region needs a strong pixel outside the band to be kept.
    """
    weak = (diff >= low).astype(np.uint8)
    opened = cv2.morphologyEx(weak, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    weak = np.where(band, opened, weak).astype(np.uint8)
    n, labels = cv2.connectedComponents(weak, connectivity=8)
    strong = np.unique(labels[(diff >= high) & ~band])
    keep = np.zeros(n, bool)
    keep[strong] = True
    keep[0] = False
    return keep[labels]


def _fill_holes(mask):
    """Fill holes so particles with see-through centres (film, foam) stay whole."""
    m = mask.astype(np.uint8)
    contours, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    filled = np.zeros_like(m)
    cv2.drawContours(filled, contours, -1, 1, thickness=cv2.FILLED)
    return filled.astype(bool)


def edge_level(region, diff, fraction=0.5, grow=2):
    """Difference value at which this particle's edge is drawn: `fraction` of its contrast.

    Contrast is the median over the particle's interior: the median copes with
    uneven particles (a pale fragment with a dark speck), and leaving out the
    outer `grow` px keeps the blurred halo from dragging it down.
    """
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * grow + 1, 2 * grow + 1))
    core = cv2.erode(region.astype(np.uint8), kernel).astype(bool)
    contrast = np.median(diff[core]) if core.sum() >= 5 else np.percentile(diff[region], 90)
    return fraction * float(contrast)


def _refine_edges(mask, diff, fraction, grow=2):
    """Move each particle's edge to where the difference falls to `fraction` of its contrast.

    Detection uses a low threshold so faint particles are found, but that puts
    the outline on the blurred halo, about 1 px outside the edge you see. The
    half-maximum rule places the edge the same way for bright and faint
    particles and for sharp or soft photos.
    """
    n, labels = cv2.connectedComponents(mask.astype(np.uint8), connectivity=8)
    out = np.zeros(mask.shape, bool)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * grow + 1, 2 * grow + 1))
    for lbl in range(1, n):
        region = labels == lbl
        near = cv2.dilate(region.astype(np.uint8), kernel).astype(bool)
        refined = near & (diff >= edge_level(region, diff, fraction, grow))
        # Only the outer edge may move. Inside, the difference can dip below the
        # edge level, e.g. where a mid-tone particle covers a blurred square
        # edge in the template, and that must not cut the particle.
        refined |= cv2.erode(region.astype(np.uint8), kernel).astype(bool)
        # Keep only the part that overlaps the detection, so a neighbour is not pulled in.
        k, parts = cv2.connectedComponents(refined.astype(np.uint8), connectivity=8)
        if k <= 1:
            continue
        overlap = np.bincount(parts[region], minlength=k)
        overlap[0] = 0
        out |= parts == int(np.argmax(overlap))
    return _fill_holes(out)


def segment(particle, template, px_per_square, params=SegmentParams()):
    """Return (labels, diff): an int32 label image (0 = background) and the difference map."""
    diff = difference(particle, template, px_per_square, params.blur_sigma)
    band = grid_band(diff.shape, px_per_square, params.grid_band_px)
    mask = _fill_holes(_hysteresis(diff, params.low, params.high, band))
    if params.edge_fraction:
        mask = _refine_edges(mask, diff, params.edge_fraction)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=8)
    h, w = mask.shape
    e = params.edge_margin_px
    out = np.zeros_like(labels)
    k = 0
    for lbl in range(1, n):
        x, y, bw, bh, area = stats[lbl]
        if area < params.min_area_px:
            continue
        if x < e or y < e or x + bw > w - e or y + bh > h - e:
            continue
        k += 1
        out[labels == lbl] = k
    return out, diff
