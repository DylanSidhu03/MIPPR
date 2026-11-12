"""The lab's old 12 x 24 checkerboard: find particles by comparing a particle photo to its empty template.

Validation only. The app takes photos on the three printed MIPPR backgrounds;
this reproduces the lab's earlier setup (fragment_area repo) so the pipeline's
measurements can be checked against the lab's ImageJ results on it
(validation/compare_imagej.py).

Both photos must already be rectified with ``board.find_board(...).rectify``
so their squares line up pixel for pixel.
"""
from dataclasses import dataclass

import cv2
import numpy as np

from mippr.segmentation.edges import fill_holes, hysteresis, refine_edges

from .board import SQUARES_X, SQUARES_Y


@dataclass
class SegmentParams:
    blur_sigma: float = 1.0  # px; smooths sensor noise and sub-pixel misalignment
    high: float = 60.0  # difference (0-255) that surely marks a particle
    low: float = 25.0  # difference that may extend a particle found with `high`
    min_area_px: int = 9  # drop specks smaller than this (about 3 x 3 px)
    grid_band_px: int = 2  # half-width of the strip along each gridline treated with suspicion
    edge_margin_px: int = 3  # blobs this close to the board edge get flag_edge (see measurement/geometry.py)
    drop_edge: bool = False  # True drops them instead of flagging (the behaviour before Output CSV draft 1)
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


def segment(particle, template, px_per_square, params=SegmentParams()):
    """Return (labels, diff): an int32 label image (0 = background) and the difference map."""
    diff = difference(particle, template, px_per_square, params.blur_sigma)
    band = grid_band(diff.shape, px_per_square, params.grid_band_px)
    # The printed frame around the board leaves the same kind of sliver as the
    # gridlines, so a strip along the outer edge gets the same treatment.
    e = params.edge_margin_px + params.grid_band_px
    band[:e, :] = band[-e:, :] = band[:, :e] = band[:, -e:] = True
    mask = fill_holes(hysteresis(diff, params.low, params.high, band))
    if params.edge_fraction:
        mask = refine_edges(mask, diff, params.edge_fraction)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=8)
    h, w = mask.shape
    e = params.edge_margin_px
    out = np.zeros_like(labels)
    k = 0
    for lbl in range(1, n):
        x, y, bw, bh, area = stats[lbl]
        if area < params.min_area_px:
            continue
        if params.drop_edge and (x < e or y < e or x + bw > w - e or y + bh > h - e):
            continue
        k += 1
        out[labels == lbl] = k
    return out, diff


WELL_COLUMNS = "ABCDEFGHIJKL"  # printed right to left across the top of the lab board


def well_id(cx, cy, px_per_square):
    """Well label for a point on the rectified board: column letter + row number.

    Columns are lettered A-L from right to left; rows are numbered 1-12 from the
    top, two squares per number, matching the printed labels when the photo is
    taken with the board upright.
    """
    col = int(cx // px_per_square)
    row = int(cy // (2 * px_per_square))
    return f"{WELL_COLUMNS[SQUARES_X - 1 - col]}{row + 1}"
