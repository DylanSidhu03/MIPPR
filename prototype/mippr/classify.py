"""Measurements and rules that the standard backgrounds make possible (spec v0.3, November 11, 2026).

- `fiber_metrics`: length along the particle's centre line and its mean width,
  so curved fibers are not under-measured by max Feret.
- `opacity`: how much of the known background is blocked by the particle.
- `color_classes`: each pixel sorted into one of the 13 colour classes, giving the
  main colour, the second colour and its share (multicolour).
- `morphology_rules`: fiber, pellet and film decided from the measurements (v2);
  everything else defaults to fragment until the image model exists (v3).

Every threshold here is a provisional starting value, to be tuned on the lab's
labelled particles (docs/LAB_DATA.md). The skeleton and shortest-path steps use
scikit-image / SciPy; the browser port needs its own thinning and a BFS over
skeleton pixels, both small.
"""
import math

import cv2
import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import dijkstra
from skimage.morphology import skeletonize

COLOR_RULES_VERSION = "0.1-provisional"

# --- Fiber length -----------------------------------------------------------


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


# --- Opacity ----------------------------------------------------------------


def opacity(img, bg_img, mask, min_px=4):
    """0 (see-through) to 1 (opaque), from the particle against the known background behind it.

    A translucent particle shows `observed = a * particle + (1 - a) * background`.
    With one background, `a` can't be separated from the particle's own colour, so
    the value is a lower bound: the share of the largest possible colour change
    (towards black on a light box, towards white on a dark box) that the particle
    reaches. Because users choose the background that contrasts with their
    particles, an opaque particle reaches most of it and a clear one little.

    Where the particle lies across two background colours (a checkerboard edge),
    it is measured directly instead: an opaque particle looks the same on both, a
    clear one shows the difference between them.

    Returns None when too few interior pixels remain (very thin particles).
    """
    m = cv2.erode(mask.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)
    if m.sum() < min_px:
        return None
    o = img[m].astype(np.float64)
    b = bg_img[m].astype(np.float64)
    gb = b.mean(axis=1)
    dark = gb < 128
    if dark.mean() > 0.2 and (~dark).mean() > 0.2:
        light_bg, dark_bg = gb[~dark].mean(), gb[dark].mean()
        if light_bg - dark_bg > 60:
            seen = abs(np.median(o[~dark].mean(axis=1)) - np.median(o[dark].mean(axis=1)))
            return float(np.clip(1 - seen / (light_bg - dark_bg), 0, 1))
    room = np.where(o < b, b, 255 - b)
    frac = np.abs(o - b) / np.maximum(room, 1.0)
    return float(np.clip(np.median(frac.max(axis=1)), 0, 1))


# --- Colour -----------------------------------------------------------------

COLOR_CLASSES = ["clear", "white", "black", "grey", "blue", "green", "red", "yellow", "orange", "brown",
                 "pink", "purple", "multicolor"]
PIXEL_CLASSES = COLOR_CLASSES[1:-1]  # clear and multicolor are particle-level decisions
CHROMA_MIN = 12.0  # below this, a pixel is white, grey or black
WHITE_L, BLACK_L = 80.0, 25.0
MULTICOLOR_SHARE = 0.20  # decided in spec v0.1: a second colour covering >= 20%
CLEAR_OPACITY = 0.5
# Neighbouring classes that shading, or a hue on a class boundary (teal, beige), produces
# on one particle. Such a pair is recorded as the second colour but doesn't make a
# particle multicolour; nor does any pair whose mean colours are closer than
# MULTICOLOR_DELTA_E (CIE76).
SHADES = {frozenset(p) for p in (("white", "grey"), ("grey", "black"), ("red", "pink"), ("red", "orange"),
                                 ("orange", "brown"), ("yellow", "brown"), ("orange", "yellow"),
                                 ("yellow", "green"), ("green", "blue"), ("blue", "purple"), ("purple", "pink"),
                                 ("red", "brown"), ("white", "yellow"), ("white", "pink"), ("grey", "brown"))}
MULTICOLOR_DELTA_E = 25.0


def lab_cie(px_bgr):
    lab = cv2.cvtColor(px_bgr.reshape(-1, 1, 3).astype(np.uint8), cv2.COLOR_BGR2LAB).reshape(-1, 3).astype(np.float64)
    return lab * [100 / 255, 1, 1] - [0, 128, 128]


def pixel_classes(lab):
    """Colour class index (into PIXEL_CLASSES) for each CIE Lab pixel. Provisional hue ranges."""
    L, a, b = lab[:, 0], lab[:, 1], lab[:, 2]
    C = np.hypot(a, b)
    h = np.degrees(np.arctan2(b, a)) % 360
    out = np.empty(len(L), object)
    grey = C < CHROMA_MIN
    out[grey & (L >= WHITE_L)] = "white"
    out[grey & (L <= BLACK_L)] = "black"
    out[grey & (L > BLACK_L) & (L < WHITE_L)] = "grey"
    col = ~grey
    red = col & ((h >= 345) | (h < 40))
    out[red] = np.where(L[red] > 65, "pink", "red")
    orange = col & (h >= 40) & (h < 75)
    out[orange] = np.where(L[orange] < 50, "brown", "orange")
    yellow = col & (h >= 75) & (h < 105)
    out[yellow] = np.where(L[yellow] < 50, "brown", "yellow")
    out[col & (h >= 105) & (h < 200)] = "green"
    out[col & (h >= 200) & (h < 295)] = "blue"
    purple = col & (h >= 295) & (h < 345)
    out[purple] = np.where(L[purple] > 70, "pink", "purple")
    # Very dark chromatic pixels read as black.
    out[col & (L <= BLACK_L * 0.6)] = "black"
    return out


def color_classes(img_bgr, mask, opacity_value=None):
    """(label, confidence, secondary, secondary_fraction) for one particle.

    Pixels inside the outline (one edge pixel removed) are sorted into classes after
    a light median filter. The most common class is the label; the next one is the
    second colour, always recorded. The particle is `multicolor` when the second
    colour covers >= 20% and isn't just a shade of the first, and `clear` when it is
    mostly see-through and nearly colourless. Confidence is the share of pixels that
    agree with the label.
    """
    m8 = mask.astype(np.uint8)
    inner = cv2.erode(m8, np.ones((3, 3), np.uint8))
    m = (inner if inner.sum() >= 4 else m8).astype(bool)
    ys, xs = np.nonzero(m)
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    crop = cv2.medianBlur(np.ascontiguousarray(img_bgr[y0:y1, x0:x1]), 3)
    px = crop[m[y0:y1, x0:x1]]
    lab = lab_cie(px)
    cls = pixel_classes(lab)
    names, counts = np.unique(cls, return_counts=True)
    order = np.argsort(-counts)
    total = counts.sum()
    main, main_share = str(names[order[0]]), counts[order[0]] / total
    second, second_share = ("", 0.0)
    if len(order) > 1:
        second, second_share = str(names[order[1]]), counts[order[1]] / total
    label, conf = main, main_share
    if second and second_share >= MULTICOLOR_SHARE and frozenset((main, second)) not in SHADES:
        de = float(np.linalg.norm(lab[cls == main].mean(axis=0) - lab[cls == second].mean(axis=0)))
        if de >= MULTICOLOR_DELTA_E:
            label, conf = "multicolor", main_share + second_share
    lab_mean = lab.mean(axis=0)
    if (opacity_value is not None and opacity_value < CLEAR_OPACITY and label != "multicolor"
            and math.hypot(lab_mean[1], lab_mean[2]) < 2 * CHROMA_MIN):
        label, conf = "clear", 1 - opacity_value
    return label, float(conf), second, float(second_share)


# --- Morphology rules (v2) ---------------------------------------------------

MORPHOLOGY_CLASSES = ["fragment", "rubbery_fragment", "fiber", "film", "foam", "pellet", "other"]
FIBER_ASPECT = 3.0  # decided: length:width >= 3:1
PELLET_CIRCULARITY, PELLET_SOLIDITY, PELLET_ASPECT = 0.85, 0.95, 1.3
FILM_OPACITY = 0.5


def _conf(value, threshold, higher_is_more, scale):
    """Confidence that a value is on the class's side of a threshold: 0.5 at the threshold."""
    if value is None or math.isnan(value):
        return 0.0
    z = (value - threshold) / scale if higher_is_more else (threshold - value) / scale
    return 1 / (1 + math.exp(-4 * max(-50.0, min(50.0, z))))  # clamped: extreme shapes mustn't overflow


def morphology_rules(aspect, circularity, solidity, opacity_value, width_unresolved=False):
    """(label, confidence, runner_up, runner_up_confidence) from the v2 rules.

    Fiber: length:width >= 3 (or too thin to measure a width). Pellet: round, solid
    and about as wide as long. Film: mostly see-through and not a fiber. Everything
    else is fragment with confidence 0.5, meaning "the rules can't tell" (rubbery
    fragment and foam need the v3 image model).
    """
    scores = {}
    scores["fiber"] = 0.99 if width_unresolved else _conf(aspect, FIBER_ASPECT, True, 1.0)
    pellet = min(_conf(circularity, PELLET_CIRCULARITY, True, 0.05),
                 _conf(solidity, PELLET_SOLIDITY, True, 0.03),
                 _conf(aspect, PELLET_ASPECT, False, 0.15))
    scores["pellet"] = pellet
    if opacity_value is not None:
        scores["film"] = min(_conf(opacity_value, FILM_OPACITY, False, 0.15), 1 - scores["fiber"])
    best = max(scores, key=scores.get)
    ranked = sorted(scores.items(), key=lambda kv: -kv[1])
    if scores[best] >= 0.5:
        runner = ranked[1] if len(ranked) > 1 else ("fragment", 0.5)
        if runner[1] < 0.5:
            runner = ("fragment", 1 - scores[best])
        return best, float(scores[best]), runner[0], float(runner[1])
    return "fragment", 0.5, ranked[0][0], float(ranked[0][1])
