"""Part 1, capture and calibration: colour correction and the photo quality check.

The scale and the flattening come from the corner markers and the grid's line
crossings (sheet.py). This file turns the printed white and grey patches into a
white balance, so colours mean the same thing on every photo, and checks a
photo before anything else runs (`check_quality`), so a community scientist
gets a plain message ("The photo is blurry ...") instead of a bad result.

Everything here uses basic OpenCV operations that OpenCV.js has (cvtColor,
Sobel, dilate, erode, fillPoly, connectedComponentsWithStats, warpPerspective).
"""
from dataclasses import asdict, dataclass

import cv2
import numpy as np

from .sheet import detect_markers, layout_from_marker_ids


def _patch_pixels(sheet, photo, inset=2.0):
    """{patch name: N x 3 BGR pixels} of the printed white and grey patches, from the marker homography."""
    canvas = sheet.rectify_sheet(photo)
    ppm = sheet.px_per_mm
    crops = {}
    for name, (x, y, w, h, _) in sheet.layout.patches_mm().items():
        crop = canvas[int((y + inset) * ppm):int((y + h - inset) * ppm), int((x + inset) * ppm):int((x + w - inset) * ppm)]
        crops[name] = crop.reshape(-1, 3).astype(np.float64)
    return crops


def white_balance(sheet, photo):
    """Per-channel gains that make the printed white patch neutral, plus how neutral the grey patch came out."""
    means = {k: v.mean(axis=0) for k, v in _patch_pixels(sheet, photo).items()}
    gains = 240.0 / np.maximum(means["white"], 1.0)
    grey = means["grey"] * gains
    return gains, {"white_patch_bgr": means["white"].round(1).tolist(), "gains_bgr": gains.round(3).tolist(),
                   "grey_patch_after_bgr": grey.round(1).tolist(),
                   "grey_spread_after": float(grey.max() - grey.min())}


# ── Photo quality check ────────────────────────────────────────────────────

@dataclass(frozen=True)
class QualityLimits:
    """Thresholds of `check_quality`, chosen on degraded synthetic photos (see capture/README.md)."""
    min_px_per_mm: float = 10.0  # a 0.5 mm particle spans >= 5 px (about 20 px of area)
    max_edge_mm: float = 0.30  # edges spread over more than this (about Gaussian sigma 0.12 mm) ...
    sharp_edge_px: float = 4.0  # ... and over more than this many px (a pixel-sharp edge measures 2-3 px;
    #                             at the pixel scale it is a resolution problem, not blur)
    max_edge_px: float = 6.0  # the limit when the scale is unknown (no markers): 0.30 mm at 20 px per mm
    min_white: float = 110.0  # the white patch (or the photo's brightest 1%) at least this grey level
    max_clipped: float = 0.10  # share of the box interiors (whole photo without a sheet) at 250 or more;
    #                            with a sheet, also more than half the white patch at 250 or more
    glare_mm2: float = 0.5  # a colourless blob inside a box, brighter than paper (1.2 x white patch), this large
    min_light_ratio: float = 0.6  # darkest / brightest white box (5th / 95th percentile)
    max_grey_spread: float = 15.0  # grey patch channel spread after white balance (grey levels)


@dataclass(frozen=True)
class Problem:
    code: str  # stable machine code: no_markers, marker_missing, low_resolution, blurry, too_dark,
    #            overexposed, glare, uneven_light, color_cast
    message: str  # plain language, for the person who took the photo
    value: float = None  # the measured value that failed
    limit: float = None

    def as_dict(self):
        return asdict(self)


CORNERS = ("top left", "top right", "bottom right", "bottom left")  # order of Layout.marker_ids()


def edge_width_px(gray, mask=None, window=21):
    """How many px the image's strong edges are spread over, (across x, across y).

    For each strong edge, its local contrast C (max - min within `window`)
    divided by its steepest gradient. A pixel-sharp step gives about 2 px, a
    step blurred by a Gaussian of sigma s gives 2.5 s, motion blur of length L
    gives about L across the motion. x and y are kept apart so motion blur in
    one direction isn't averaged away by the sharp edges along it. A low
    percentile over the edges is used (the sharpest quarter): focus and shake
    blur every edge alike, while shadows, textures and soft particle rims only
    add wide ones.
    """
    g = gray.astype(np.float32)
    k = np.ones((window, window), np.uint8)
    contrast = cv2.dilate(g, k) - cv2.erode(g, k)
    out = []
    for dx, dy, line in ((1, 0, np.ones((1, 3), np.uint8)), (0, 1, np.ones((3, 1), np.uint8))):
        grad = np.abs(cv2.Sobel(g, cv2.CV_32F, dx, dy, ksize=3)) / 8.0
        other = np.abs(cv2.Sobel(g, cv2.CV_32F, dy, dx, ksize=3)) / 8.0
        peak = grad >= cv2.dilate(grad, line)  # steepest point across the edge
        sel = peak & (contrast >= 40) & (grad > other) & (grad >= contrast / (window + 1))
        if mask is not None:
            sel &= mask
        w = contrast[sel] / grad[sel]
        out.append(float(np.percentile(w, 25)) if w.size >= 50 else float("nan"))
    return tuple(out)


def _grid_mask(sheet, shape):
    """The grid area in photo px (from the refined crossings), shrunk by a third of a box."""
    c = sheet.crossings
    ring = np.vstack([c[0, :], c[1:, -1], c[-1, -2::-1], c[-2:0:-1, 0]])
    mask = np.zeros(shape[:2], np.uint8)
    cv2.fillPoly(mask, [np.round(ring).astype(np.int32)], 1)
    k = max(3, int(sheet.box_px / 3))
    return cv2.erode(mask, np.ones((k, k), np.uint8)).astype(bool)


def _box_mask(sheet, shape, keep=0.7):
    """The middle `keep` of every box in photo px: paper or particle, no printed lines."""
    c = sheet.crossings
    mask = np.zeros(shape[:2], np.uint8)
    for r in range(sheet.layout.rows):
        for col in range(sheet.layout.cols):
            quad = c[[r, r, r + 1, r + 1], [col, col + 1, col + 1, col]]
            mid = quad.mean(axis=0)
            cv2.fillPoly(mask, [np.round(mid + (quad - mid) * keep).astype(np.int32)], 1)
    return mask.astype(bool)


def _white_boxes(sheet, gray):
    """90th-percentile grey level near the centre of every white box (paper level, not the particle)."""
    lay = sheet.layout
    if lay.background == "black_grid":
        return np.array([])
    c, half = sheet.crossings, max(2, int(sheet.box_px * 0.3))
    levels = []
    for r in range(lay.rows):
        for col in range(lay.cols):
            if lay.background == "checkerboard" and (r + col) % 2:
                continue
            x, y = np.round(c[r:r + 2, col:col + 2].reshape(-1, 2).mean(axis=0)).astype(int)
            win = gray[max(0, y - half):y + half, max(0, x - half):x + half]
            if win.size:
                levels.append(np.percentile(win, 90))
    return np.array(levels)


def measure_quality(photo, sheet=None):
    """The numbers `check_quality` judges, as a dict (also worth keeping in run.json).

    Keys: markers_found (of 4; None if no sheet's markers at all), missing_corners,
    px_per_mm, edge_width_px (x, y), edge_width_mm, white_level, clipped_share,
    and with a sheet: white_clipped, glare_mm2, light_ratio, grey_spread.
    """
    gray = cv2.cvtColor(photo, cv2.COLOR_BGR2GRAY)
    m = {}

    # Markers: which of the four corners were found.
    found = detect_markers(photo)
    layout = sheet.layout if sheet is not None else None
    if layout is None:
        try:
            layout = layout_from_marker_ids(found)
        except ValueError:
            pass
    ppm = None
    if layout is None:
        m["markers_found"], m["missing_corners"] = None, list(CORNERS)
    else:
        ids = layout.marker_ids()
        m["missing_corners"] = [name for i, name in zip(ids, CORNERS) if i not in found]
        m["markers_found"] = 4 - len(m["missing_corners"])
        if sheet is not None:
            ppm = sheet.px_per_mm
        else:  # the markers alone still give the scale
            sides = [np.linalg.norm(np.roll(v, -1, axis=0) - v, axis=1).mean() for k, v in found.items() if k in ids]
            ppm = float(np.mean(sides)) / layout.marker_mm if sides else None
    m["px_per_mm"] = None if ppm is None else round(float(ppm), 2)

    # Blur: how wide the printed edges (or, without a sheet, any strong edges) are.
    grid = _grid_mask(sheet, photo.shape) if sheet is not None else None
    window = int(max(7, round(1.5 * ppm)) // 2 * 2 + 1) if ppm else 21
    wx, wy = edge_width_px(gray, grid, window)
    m["edge_width_px"] = [None if np.isnan(v) else round(v, 2) for v in (wx, wy)]  # None: too few edges
    width = max(wx, wy) if not (np.isnan(wx) or np.isnan(wy)) else (wy if np.isnan(wx) else wx)
    m["edge_width_mm"] = None if (ppm is None or np.isnan(width)) else round(float(width / ppm), 3)

    # Exposure: the printed white patch with a sheet, else the photo's brightest 1%.
    boxes = _box_mask(sheet, photo.shape) if sheet is not None else np.ones(gray.shape, bool)
    m["clipped_share"] = round(float((photo.max(axis=2) >= 250)[boxes].mean()), 4)
    if sheet is not None:
        # Medians, because under lens distortion the patch's printed frame can creep into the crop.
        px = _patch_pixels(sheet, photo)
        patches = {k: np.median(v, axis=0) for k, v in px.items()}
        m["white_level"] = round(float(patches["white"].mean()), 1)
        m["white_clipped"] = round(float((px["white"].max(axis=1) >= 250).mean()), 3)
    else:
        m["white_level"] = round(float(np.percentile(gray, 99)), 1)

    if sheet is not None:
        # Glare: the largest colourless blob inside any box that is brighter than paper can be
        # (well above the printed white patch, or clipped).
        shiny = (photo.min(axis=2) >= min(250.0, 1.2 * m["white_level"])) & boxes
        n, _, stats, _ = cv2.connectedComponentsWithStats(shiny.astype(np.uint8), connectivity=8)
        m["glare_mm2"] = round(float(stats[1:, cv2.CC_STAT_AREA].max() / ppm ** 2) if n > 1 else 0.0, 2)
        # Uneven light (e.g. the phone's shadow): darkest against brightest white boxes.
        levels = _white_boxes(sheet, gray)
        m["light_ratio"] = (round(float(np.percentile(levels, 5) / max(np.percentile(levels, 95), 1.0)), 3)
                            if levels.size >= 10 else None)
        # Colour cast left after white balance: the grey patch should come out grey.
        gains = 240.0 / np.maximum(patches["white"], 1.0)
        m["grey_spread"] = round(float(np.ptp(patches["grey"] * gains)), 1)
    return m


def check_quality(photo, sheet=None, limits=QualityLimits(), metrics=None):
    """Reasons a photo can't give good results, before anything else runs. Empty list = fine.

    `photo` is the BGR photo as taken. With `sheet` (from `find_sheet`) the
    checks look inside the grid and use the printed white and grey patches;
    without it (or when the sheet can't be found) the checks that don't need
    it run on the whole photo. Each problem has a stable `code` and a short
    `message` for the person who took the photo. Pass `metrics` from
    `measure_quality` to avoid measuring twice.
    """
    L = limits
    m = metrics if metrics is not None else measure_quality(photo, sheet)
    probs = []
    if m["markers_found"] is None:
        probs.append(Problem("no_markers", "No MIPPR sheet found. Photos must be taken on one of the printed "
                             "MIPPR backgrounds (white grid, black grid or checkerboard), with the whole "
                             "sheet and all four black corner squares in view.", 0, 4))
    elif m["missing_corners"]:
        probs.append(Problem("marker_missing", f"Corner marker missing ({', '.join(m['missing_corners'])}). Keep "
                             "all four black corner squares in the photo, uncovered and in focus.",
                             m["markers_found"], 4))

    ppm = m["px_per_mm"]
    if ppm is not None and ppm < L.min_px_per_mm:
        probs.append(Problem("low_resolution", f"Not enough detail: a 0.5 mm particle would be only {ppm * 0.5:.1f} "
                             "pixels across. Use the camera's full resolution (no zoom, no reduced size) and fill "
                             "the frame with the sheet.", ppm, L.min_px_per_mm))

    edge_px = max((v for v in m["edge_width_px"] if v is not None), default=None)
    if m["edge_width_mm"] is not None:
        value, limit = m["edge_width_mm"], L.max_edge_mm
        blurry = value > limit and edge_px > L.sharp_edge_px
    else:
        value, limit = edge_px, L.max_edge_px
        blurry = value is not None and value > limit
    if blurry:
        probs.append(Problem("blurry", "The photo is blurry. Hold the phone still, tap the sheet to focus, and "
                             "use more light.", value, limit))

    if m["white_level"] < L.min_white:
        probs.append(Problem("too_dark", "The photo is too dark. Add light or move to a brighter place (no flash).",
                             m["white_level"], L.min_white))
    overexposed = m["clipped_share"] > L.max_clipped or m.get("white_clipped", 0) > 0.5
    if overexposed:
        probs.append(Problem("overexposed", "The photo is too bright: parts of it are pure white, so pale "
                             "particles disappear. Use less light or tap the sheet to set the exposure.",
                             m["clipped_share"], L.max_clipped))

    if sheet is not None:
        if not overexposed and m["glare_mm2"] >= L.glare_mm2:
            probs.append(Problem("glare", "Glare on the sheet. Move the light to the side or use diffuse light, and "
                                 "don't use the flash.", m["glare_mm2"], L.glare_mm2))
        if m["light_ratio"] is not None and m["light_ratio"] < L.min_light_ratio:
            probs.append(Problem("uneven_light", "The light is uneven (a shadow?). Light the sheet evenly and keep "
                                 "your shadow and the phone's off it.", m["light_ratio"], L.min_light_ratio))
        if not overexposed and m["grey_spread"] > L.max_grey_spread:
            probs.append(Problem("color_cast", "Colours may be off: the grey patch is still tinted after white "
                                 "balance. Use one kind of light (daylight or one lamp), not a mix.",
                                 m["grey_spread"], L.max_grey_spread))
    return probs
