"""Deterministic size, shape and colour measurements from particle masks.

No model is involved, so the same mask always gives the same numbers.

Geometry follows ImageJ's conventions so results can be compared with the
lab's current workflow: area is the pixel count, and Feret diameters are taken
over the outer edges of the boundary pixels (so a single pixel has Feret
sqrt(2) px and MinFeret 1 px, as in ImageJ).
"""
import math

import cv2
import numpy as np

from .board import SQUARES_X

WELL_COLUMNS = "ABCDEFGHIJKL"  # printed right to left across the top of the lab board


def _hull_of_pixel_corners(contour):
    pts = contour.reshape(-1, 2).astype(np.float32)
    offs = np.array([[-0.5, -0.5], [0.5, -0.5], [0.5, 0.5], [-0.5, 0.5]], np.float32)
    corners = (pts[:, None, :] + offs[None]).reshape(-1, 2)
    return cv2.convexHull(corners).reshape(-1, 2).astype(np.float64)


def feret(hull):
    """(max Feret, min Feret, max Feret angle in degrees) of a convex polygon, in px."""
    d = hull[:, None, :] - hull[None, :, :]
    dist = np.hypot(d[..., 0], d[..., 1])
    i, j = np.unravel_index(np.argmax(dist), dist.shape)
    a, b = hull[i], hull[j]
    if a[0] > b[0]:
        a, b = b, a
    angle = math.degrees(math.atan2(-(b[1] - a[1]), b[0] - a[0])) % 180  # y points down
    # Rotating calipers: the minimum width is found perpendicular to a hull edge.
    edges = np.roll(hull, -1, axis=0) - hull
    lengths = np.hypot(edges[:, 0], edges[:, 1])
    edges = edges[lengths > 0] / lengths[lengths > 0, None]
    normals = np.stack([-edges[:, 1], edges[:, 0]], axis=1)
    proj = hull @ normals.T
    min_width = float((proj.max(axis=0) - proj.min(axis=0)).min())
    return float(dist[i, j]), min_width, angle


def well_id(cx, cy, px_per_square):
    """Well label for a point on the rectified board: column letter + row number.

    Columns are lettered A-L from right to left; rows are numbered 1-12 from the
    top, two squares per number, matching the printed labels when the photo is
    taken with the board upright.
    """
    col = int(cx // px_per_square)
    row = int(cy // (2 * px_per_square))
    return f"{WELL_COLUMNS[SQUARES_X - 1 - col]}{row + 1}"


def _color_stats(img_bgr, mask):
    """Mean and standard deviation of RGB, HSV and Lab inside the mask.

    Edge pixels mix particle and background colour, so the mask is eroded by
    one pixel when enough pixels remain.
    """
    m = mask.astype(np.uint8)
    inner = cv2.erode(m, np.ones((3, 3), np.uint8))
    if inner.sum() >= 4:
        m = inner
    px = img_bgr[m.astype(bool)].reshape(-1, 1, 3)
    out = {"color_px": int(px.shape[0])}
    rgb = px[..., ::-1].reshape(-1, 3).astype(np.float64)
    hsv = cv2.cvtColor(px, cv2.COLOR_BGR2HSV_FULL).reshape(-1, 3).astype(np.float64)
    lab = cv2.cvtColor(px, cv2.COLOR_BGR2LAB).reshape(-1, 3).astype(np.float64)
    # OpenCV stores 8-bit Lab as L*255/100 and a+128, b+128; convert back to CIE units.
    lab = lab * [100 / 255, 1, 1] - [0, 128, 128]
    for name, vals in (("R", rgb[:, 0]), ("G", rgb[:, 1]), ("B", rgb[:, 2]),
                       ("S", hsv[:, 1]), ("V", hsv[:, 2]),
                       ("L", lab[:, 0]), ("a", lab[:, 1]), ("b", lab[:, 2])):
        out[f"{name}_mean"] = float(vals.mean())
        out[f"{name}_sd"] = float(vals.std())
    # Hue is an angle, so average it on the circle (0-360 degrees).
    h = np.radians(hsv[:, 0] * 360 / 256)
    out["H_mean"] = float(math.degrees(math.atan2(np.sin(h).mean(), np.cos(h).mean())) % 360)
    out["H_sd"] = float(math.degrees(math.sqrt(max(0.0, -2 * math.log(
        max(1e-12, math.hypot(np.sin(h).mean(), np.cos(h).mean())))))))
    return out


def measure(labels, img_bgr, um_per_px, px_per_square):
    """One dict per particle with geometry in um / um^2 and colour statistics."""
    rows = []
    for lbl in range(1, int(labels.max()) + 1):
        mask = labels == lbl
        area_px = int(mask.sum())
        if area_px == 0:
            continue
        m8 = mask.astype(np.uint8)
        contours, _ = cv2.findContours(m8, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        contour = max(contours, key=len)
        hull = _hull_of_pixel_corners(contour)
        f_max, f_min, f_angle = feret(hull)
        perim = cv2.arcLength(contour, True) if len(contour) > 1 else 4.0
        convex_area = cv2.contourArea(hull.astype(np.float32))
        convex_perim = cv2.arcLength(hull.astype(np.float32), True)
        ys, xs = np.nonzero(mask)
        cx, cy = xs.mean(), ys.mean()
        x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
        (_, _), (rw, rh), _ = cv2.minAreaRect(hull.astype(np.float32))
        u, u2 = um_per_px, um_per_px ** 2
        row = {
            "particle": lbl,
            "well": well_id(cx, cy, px_per_square),
            "x_um": cx * u,
            "y_um": cy * u,
            "area_um2": area_px * u2,
            "area_px": area_px,
            "perimeter_um": perim * u,
            "convex_area_um2": convex_area * u2,
            "convex_perimeter_um": convex_perim * u,
            "feret_max_um": f_max * u,
            "feret_min_um": f_min * u,
            "feret_angle_deg": f_angle,
            "ced_um": 2 * math.sqrt(area_px / math.pi) * u,
            "bbox_width_um": (x1 - x0 + 1) * u,
            "bbox_height_um": (y1 - y0 + 1) * u,
            "min_rect_length_um": max(rw, rh) * u,
            "min_rect_width_um": min(rw, rh) * u,
            "aspect_ratio": f_max / f_min if f_min > 0 else float("nan"),
            "circularity": min(1.0, 4 * math.pi * area_px / perim ** 2) if perim > 0 else float("nan"),
            "solidity": min(1.0, area_px / convex_area) if convex_area > 0 else float("nan"),
        }
        row.update(_color_stats(img_bgr, mask))
        rows.append(row)
    return rows
