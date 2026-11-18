"""Particle crops: one small image per particle, with the background made transparent.

Saved next to particles.csv (`crops/<particle_ref>.png`, column `crop_file`) so each row links to its
picture, for review, storage (Drive open question 9b) and training the v3 morphology model. The crop is
cut from the white-balanced, flattened grid at full resolution: square, centred on the particle, padded,
and with alpha 0 outside the particle's outline (dilated by one pixel), so the pixels themselves are
kept and the background can be put back as any colour.
"""
import cv2
import numpy as np

PAD_FRAC = 0.15  # padding round the particle, as a share of its larger side
PAD_MIN_PX = 4


def crop_box(x, y, w, h, shape, pad_frac=PAD_FRAC):
    """(x0, y0, x1, y1): a square window round the box (x, y, w, h), padded, clipped to `shape` (h, w)."""
    side = max(w, h)
    side += 2 * max(PAD_MIN_PX, int(round(pad_frac * side)))
    cx2, cy2 = 2 * x + w, 2 * y + h  # twice the centre, to stay in integers
    x0, y0 = (cx2 - side) // 2, (cy2 - side) // 2
    return max(0, x0), max(0, y0), min(shape[1], x0 + side), min(shape[0], y0 + side)


def crop_particle(img_bgr, mask, box=None, pad_frac=PAD_FRAC):
    """BGRA crop of one particle: `img_bgr` inside the window, alpha 255 on the (1 px dilated) mask.

    `mask` is the particle's boolean mask over the whole image; `box` its (x, y, w, h), found from the
    mask if not given.
    """
    if box is None:
        ys, xs = np.nonzero(mask)
        box = (xs.min(), ys.min(), xs.max() - xs.min() + 1, ys.max() - ys.min() + 1)
    x0, y0, x1, y1 = crop_box(*box, mask.shape, pad_frac)
    m = cv2.dilate(mask[y0:y1, x0:x1].astype(np.uint8), np.ones((3, 3), np.uint8))
    out = np.dstack([img_bgr[y0:y1, x0:x1], m * 255]).astype(np.uint8)
    return out


def write_crops(out_dir, labels, balanced, measured, rows):
    """Write crops/<particle_ref>.png for every row (rows and measured matched by particle number)."""
    (out_dir / "crops").mkdir(parents=True, exist_ok=True)
    for row, m in zip(rows, sorted(measured, key=lambda m: m["particle"])):  # build_rows orders rows by particle
        px = m["_px"]
        crop = crop_particle(balanced, labels == m["particle"], (px["x"], px["y"], px["w"], px["h"]))
        cv2.imwrite(str(out_dir / row["crop_file"]), crop)
