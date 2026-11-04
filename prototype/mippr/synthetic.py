"""Synthetic 'photos' of printed sheets, for tests and for trying settings without a camera.

A sheet is rendered, particles are drawn into chosen boxes, and the page is
photographed in software: a perspective tilt, barrel lens distortion, uneven
light, blur and sensor noise.
"""
import cv2
import numpy as np

from .grid import Layout, render


def sheet_bgr(layout, dpi):
    g = render(layout, dpi)
    return cv2.cvtColor(g, cv2.COLOR_GRAY2BGR)


def draw_particle(img, layout, dpi, box, shape="disc", size_mm=2.0, color=(40, 40, 200), offset_mm=(0, 0),
                  angle=0.0, aspect=1.0):
    """Draw a particle centred in a box (e.g. 'B4'), optionally shifted by offset_mm."""
    ppm = dpi / 25.4
    row = ord(box[0]) - ord("A")
    col = int(box[1:]) - 1
    gx, gy = layout.grid_origin_mm
    cx = (gx + (col + 0.5) * layout.box_mm + offset_mm[0]) * ppm
    cy = (gy + (row + 0.5) * layout.box_mm + offset_mm[1]) * ppm
    if shape == "disc":
        cv2.circle(img, (int(round(cx)), int(round(cy))), int(round(size_mm / 2 * ppm)), color, -1, cv2.LINE_AA)
    else:  # rectangle or fiber: size_mm long, size_mm/aspect wide
        box_pts = cv2.boxPoints(((cx, cy), (size_mm * ppm, size_mm / aspect * ppm), angle))
        cv2.fillPoly(img, [np.round(box_pts).astype(np.int32)], color, cv2.LINE_AA)
    return img


def photograph(img, seed=0, tilt=0.04, k1=-0.04, out_width=2400, blur=1.0, noise=2.0, light=0.15):
    """Return (photo, true mapping not needed) with tilt, barrel distortion, vignetting, blur and noise."""
    rng = np.random.default_rng(seed)
    h, w = img.shape[:2]
    pad = int(0.08 * w)
    big = cv2.copyMakeBorder(img, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=(90, 80, 70))
    H, W = big.shape[:2]
    src = np.float32([[0, 0], [W, 0], [W, H], [0, H]])
    dst = (src + rng.uniform(-tilt, tilt, (4, 2)) * [W, H]).astype(np.float32)
    M = cv2.getPerspectiveTransform(src, dst)
    warped = cv2.warpPerspective(big, M, (W, H), borderValue=(90, 80, 70))
    # Barrel distortion around the centre.
    yy, xx = np.indices((H, W), dtype=np.float32)
    cx, cy = W / 2, H / 2
    nx, ny = (xx - cx) / cx, (yy - cy) / cx
    r2 = nx ** 2 + ny ** 2
    f = 1 + k1 * r2
    map_x, map_y = (nx * f * cx + cx).astype(np.float32), (ny * f * cx + cy).astype(np.float32)
    photo = cv2.remap(warped, map_x, map_y, cv2.INTER_LINEAR, borderValue=(90, 80, 70))
    s = out_width / W
    photo = cv2.resize(photo, None, fx=s, fy=s, interpolation=cv2.INTER_AREA).astype(np.float32)
    # Uneven light: brighter at one side.
    gy, gx = np.indices(photo.shape[:2], dtype=np.float32)
    shade = 1 - light * (gx / photo.shape[1])
    photo = photo * shade[..., None]
    photo = cv2.GaussianBlur(photo, (0, 0), blur) + rng.normal(0, noise, photo.shape)
    return np.clip(photo, 0, 255).astype(np.uint8)
