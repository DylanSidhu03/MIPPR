"""Part 4, colour: sort each pixel into one of the 13 colour classes, then label the particle.

The particle gets its main colour, its second colour and that colour's share. It is
`multicolor` when the second colour covers >= 20% and is clearly different, and
`clear` when it is mostly see-through and nearly colourless (opacity from
measurement/opacity.py).

The hue and lightness ranges are provisional starting values (COLOR_RULES_VERSION).
They are to be fitted on the lab's labelled particles (part 7).
"""
import math

import cv2
import numpy as np

COLOR_RULES_VERSION = "0.1-provisional"

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
    return label_from_lab(lab_cie(px), opacity_value)


def label_from_lab(lab, opacity_value=None):
    """The particle-level decision of color_classes, from its CIE Lab pixels (used for fitting too)."""
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
