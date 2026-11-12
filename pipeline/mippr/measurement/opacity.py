"""Part 3, measurement: how much of the known background a particle blocks (spec v0.3).

Possible because the printed background behind every particle is known. Used by the
colour rules (clear vs white) and the morphology rules (film).
"""
import cv2
import numpy as np


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
