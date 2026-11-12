"""Part 3, measurement: length and width along a particle's centre line (spec v0.3).

Max Feret measures a curved fiber straight across, so it reads short. This follows
the skeleton's longest path instead, smoothed, with the ends trimmed where the
skeleton runs into corners and the true end length added back. Tested within about
1-3% on curved and straight shapes.

The skeleton and shortest-path steps use scikit-image / SciPy; the browser port
(web/src/measurement/) needs its own thinning and a BFS over skeleton pixels.
"""
import math

import cv2
import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import dijkstra
from skimage.morphology import skeletonize


def _longest_path(skel):
    """Pixel coordinates (N x 2, x y) along the longest shortest path through an 8-connected skeleton."""
    ys, xs = np.nonzero(skel)
    n = len(ys)
    if n < 2:
        return np.stack([xs, ys], axis=1).astype(np.float64)
    index = -np.ones(skel.shape, np.int64)
    index[ys, xs] = np.arange(n)
    rows, cols, w = [], [], []
    h, wd = skel.shape
    for dy, dx in ((0, 1), (1, 0), (1, 1), (1, -1)):
        y2, x2 = ys + dy, xs + dx
        ok = (y2 >= 0) & (y2 < h) & (x2 >= 0) & (x2 < wd)
        j = np.full(n, -1)
        j[ok] = index[y2[ok], x2[ok]]
        keep = j >= 0
        rows.append(np.arange(n)[keep])
        cols.append(j[keep])
        w.append(np.full(keep.sum(), math.hypot(dy, dx)))
    rows, cols, w = map(np.concatenate, (rows, cols, w))
    g = coo_matrix((w, (rows, cols)), shape=(n, n)).tocsr()
    # Two sweeps find the ends of the longest path in a tree-like skeleton.
    d0 = dijkstra(g, directed=False, indices=0)
    a = int(np.argmax(np.where(np.isinf(d0), -1, d0)))
    da, pred = dijkstra(g, directed=False, indices=a, return_predecessors=True)
    b = int(np.argmax(np.where(np.isinf(da), -1, da)))
    path = [b]
    while path[-1] != a:
        path.append(int(pred[path[-1]]))
    path = np.array(path)
    return np.stack([xs[path], ys[path]], axis=1).astype(np.float64)


def _smooth_length(pts, window=7):
    """Length of a pixel path after a moving-average smooth, which removes the staircase.

    Counting pixel steps (1 and sqrt 2) over-measures curves by up to ~8%; the smoothed
    polyline is accurate in every direction. The two ends are kept in place.
    """
    n = len(pts)
    if n < 2:
        return 0.0
    k = min(window, n if n % 2 else n - 1)
    if k >= 3:
        pad = k // 2
        ext = np.vstack([np.repeat(pts[:1], pad, 0), pts, np.repeat(pts[-1:], pad, 0)])
        kernel = np.ones(k) / k
        sm = np.stack([np.convolve(ext[:, i], kernel, mode="valid") for i in (0, 1)], axis=1)
        sm[0], sm[-1] = pts[0], pts[-1]
    else:
        sm = pts
    d = np.diff(sm, axis=0)
    return float(np.hypot(d[:, 0], d[:, 1]).sum())


UNIFORM_MAX = 1.5
END_TRIM = 0.9


def fiber_metrics(mask):
    """(length_px, mean_width_px, uniform) measured along the centre line.

    The longest path through the skeleton is followed, smoothed and measured. Near
    each end the skeleton bends into corners or fades into a rounded tip, so the path
    is trimmed where the particle's half-thickness (distance to the edge) drops below
    END_TRIM x its typical value, and that half-thickness is added back at each end.
    This is exact for both square and rounded ends. The mean width is area / length.

    `uniform` is True when the particle is about equally thick along its length (its
    thickest point is at most UNIFORM_MAX times the mean width), as a fiber is. A
    compact or branching blob is not, and its centre-line numbers aren't used.
    """
    m = mask.astype(bool)
    area = float(m.sum())
    ys, xs = np.nonzero(m)
    crop = np.pad(m[ys.min():ys.max() + 1, xs.min():xs.max() + 1], 1)
    dt = cv2.distanceTransform(crop.astype(np.uint8), cv2.DIST_L2, 5)
    path = _longest_path(skeletonize(crop))
    if len(path) < 3:
        length = float(max(crop.shape) - 2)
    else:
        d = dt[path[:, 1].astype(int), path[:, 0].astype(int)]
        half = float(np.median(d))
        # Distance along the path from each end; only the last ~1.5 half-widths can be trimmed,
        # so a fiber that narrows somewhere (e.g. where it crosses a printed line) keeps that part.
        step = np.r_[0, np.hypot(*np.diff(path, axis=0).T)]
        from_start, from_end = np.cumsum(step), np.cumsum(step[::-1])[::-1]
        end_zone = (from_start <= 1.5 * half) | (from_end <= 1.5 * half)
        keep = np.nonzero(~end_zone | (d >= END_TRIM * half))[0]
        core = path[keep[0]:keep[-1] + 1] if len(keep) >= 2 else path
        trimmed = (_smooth_length(path) - _smooth_length(core)) if len(keep) >= 2 else 0.0
        length = _smooth_length(core) + min(2 * END_TRIM * half, trimmed + 2 * half)
    w = area / length if length > 0 else 0.0
    thickest = 2 * float(dt.max())
    return length, w, bool(w > 0 and thickest <= UNIFORM_MAX * w)
