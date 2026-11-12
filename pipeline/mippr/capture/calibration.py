"""Part 1, capture and calibration: colour correction from the printed patches.

The scale and the flattening come from the corner markers and the grid's line
crossings (sheet.py). This file turns the printed white and grey patches into a
white balance, so colours mean the same thing on every photo.

Still to build here (see README.md): an image quality check (blur, darkness,
glare, all four markers in frame) that runs before anything else.
"""
import numpy as np


def white_balance(sheet, photo):
    """Per-channel gains that make the printed white patch neutral, plus how neutral the grey patch came out."""
    canvas = sheet.rectify_sheet(photo)
    ppm = sheet.px_per_mm
    means = {}
    for name, (x, y, w, h, _) in sheet.layout.patches_mm().items():
        inset = 2.0
        crop = canvas[int((y + inset) * ppm):int((y + h - inset) * ppm), int((x + inset) * ppm):int((x + w - inset) * ppm)]
        means[name] = crop.reshape(-1, 3).astype(np.float64).mean(axis=0)
    gains = 240.0 / np.maximum(means["white"], 1.0)
    grey = means["grey"] * gains
    return gains, {"white_patch_bgr": means["white"].round(1).tolist(), "gains_bgr": gains.round(3).tolist(),
                   "grey_patch_after_bgr": grey.round(1).tolist(),
                   "grey_spread_after": float(grey.max() - grey.min())}


# --- Planned -------------------------------------------------------------------

def check_quality(photo, sheet=None):
    """Planned: reasons a photo can't give good results, before anything else runs.

    Returns a list of problems (empty if the photo is fine), each a short message for
    the user, e.g. "The photo is blurry", "Corner marker missing (top right)",
    "Too dark", "Glare on the sheet", "Too few pixels per mm for 0.5 mm particles".

    Checks to implement:
    - blur: variance of the Laplacian inside the grid
    - exposure: share of clipped pixels; the white patch's level
    - glare: bright, low-saturation blobs inside boxes
    - markers: all four found (`sheet.markers_found`)
    - resolution: `sheet.px_per_mm` against the smallest particle size
    """
    raise NotImplementedError("Part 1: photo quality check is planned (see capture/README.md)")
