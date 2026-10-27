"""Deterministic size, shape and colour measurements from particle masks.

No model is involved, so the same mask always gives the same numbers.

Geometry follows ImageJ's conventions so results can be compared with the
lab's current workflow: area is the pixel count, and Feret diameters are taken
over the outer edges of the boundary pixels (so a single pixel has Feret
sqrt(2) px and MinFeret 1 px, as in ImageJ).

Perimeter is the exception. The main `perimeter_um` and `circularity` use a
sub-pixel outline, which scripts/perimeter_study.py found to be the most
accurate and the least affected by rotation. ImageJ-compatible values are
kept alongside as `perimeter_imagej_um` and `circularity_imagej`. Which one
is reported as the headline number is a provisional decision
(docs/CLASSIFICATION_SPEC.md).
"""
import math

import cv2
import numpy as np
from skimage.measure import find_contours

from .board import SQUARES_X
from .segment import edge_level, grid_band

WELL_COLUMNS = "ABCDEFGHIJKL"  # printed right to left across the top of the lab board


def _hull_of_pixel_corners(contour):
    pts = contour.reshape(-1, 2).astype(np.float32)
    offs = np.array([[-0.5, -0.5], [0.5, -0.5], [0.5, 0.5], [-0.5, 0.5]], np.float32)
    corners = (pts[:, None, :] + offs[None]).reshape(-1, 2)
    return cv2.convexHull(corners).reshape(-1, 2).astype(np.float64)


def subpixel_outline(mask, diff=None, level=None, pad=4):
    """Sub-pixel outline (N x 2 array of x, y) of one particle.

    With a difference map, the outline is the iso-line at the particle's edge
    level, found by marching squares, so it follows the real edge between
    pixels. Without one it falls back to the iso-line of the mask itself.
    """
    ys, xs = np.nonzero(mask)
    y0, x0 = max(0, ys.min() - pad), max(0, xs.min() - pad)
    y1, x1 = ys.max() + pad + 1, xs.max() + pad + 1
    m = mask[y0:y1, x0:x1]
    if diff is None:
        field, level = m.astype(np.float64), 0.5
    else:
        # Only look near this particle, so a neighbour's edge is never traced.
        near = cv2.dilate(m.astype(np.uint8), np.ones((5, 5), np.uint8)).astype(bool)
        field = np.where(near, diff[y0:y1, x0:x1], 0).astype(np.float64)
        # The difference can dip inside a particle, e.g. where it crosses a
        # printed square edge. Keep the interior above the level so only the
        # outer edge is traced.
        inner = cv2.erode(m.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)
        field[inner] = np.maximum(field[inner], 2 * level)
    field = np.pad(field, 1)
    lines = find_contours(field, level)
    line = max(lines, key=len)
    return line[:, ::-1] - 1 + [x0, y0]


def _polygon_length_area(pts):
    d = np.diff(np.vstack([pts, pts[:1]]), axis=0)
    length = float(np.hypot(d[:, 0], d[:, 1]).sum())
    area = 0.5 * abs(float(np.dot(pts[:, 0], np.roll(pts[:, 1], -1)) - np.dot(pts[:, 1], np.roll(pts[:, 0], -1))))
    return length, area


def perimeter_imagej(mask):
    """Perimeter as ImageJ computes it for traced particles (PolygonRoi.getTracedPerimeter).

    Walks the outline along pixel edges and subtracts (2 - sqrt 2) for every
    other corner, which approximates cutting the corners diagonally.
    """
    pts = _crack_vertices(mask)
    n = len(pts)
    if n < 4:
        return 0.0
    sumdx = sumdy = n_corners = 0
    dx1, dy1 = pts[0] - pts[-1]
    side1 = abs(dx1) + abs(dy1)
    corner = False
    for i in range(n):
        dx2, dy2 = pts[(i + 1) % n] - pts[i]
        sumdx += abs(dx1)
        sumdy += abs(dy1)
        side2 = abs(dx2) + abs(dy2)
        if side1 > 1 or not corner:
            corner = True
            n_corners += 1
        else:
            corner = False
        dx1, dy1, side1 = dx2, dy2, side2
    return float(sumdx + sumdy - n_corners * (2 - math.sqrt(2)))


def _crack_vertices(mask):
    """Vertices (integer pixel-corner coordinates) of the outer pixel-edge boundary, in order.

    Only the points where the boundary turns are returned, as in ImageJ's traced
    polygons.
    """
    m = np.pad(mask.astype(bool), 1)
    # Walk the boundary keeping the particle on the right-hand side.
    ys, xs = np.nonzero(m)
    start = (xs[np.argmin(ys * m.shape[1] + xs)], ys.min())  # top-left pixel's top-left corner
    x, y = start
    d = (1, 0)  # moving right along the top edge
    pts = [(x, y)]

    def inside(px, py):
        return 0 <= py < m.shape[0] and 0 <= px < m.shape[1] and m[py, px]

    while True:
        dx, dy = d
        # Pixels ahead-left and ahead-right of the current edge, seen in the direction of travel.
        if d == (1, 0):
            left, right = inside(x, y - 1), inside(x, y)
        elif d == (0, 1):
            left, right = inside(x, y), inside(x - 1, y)
        elif d == (-1, 0):
            left, right = inside(x - 1, y), inside(x - 1, y - 1)
        else:
            left, right = inside(x - 1, y - 1), inside(x, y - 1)
        if left:
            nd = (dy, -dx)  # turn left
        elif right:
            nd = d  # straight on
        else:
            nd = (-dy, dx)  # turn right
        if nd != d:
            pts.append((x, y))
            d = nd
        x, y = x + d[0], y + d[1]
        if (x, y) == start:
            break
    pts = np.array(pts[1:] if pts[0] == pts[1] else pts, dtype=np.int64)
    # Drop a duplicated start vertex and any collinear points.
    keep = []
    n = len(pts)
    for i in range(n):
        a, b, c = pts[i - 1], pts[i], pts[(i + 1) % n]
        if (b - a)[0] * (c - b)[1] - (b - a)[1] * (c - b)[0] != 0:
            keep.append(b)
    return np.array(keep) - 1


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


def measure(labels, img_bgr, um_per_px, px_per_square, diff=None, edge_fraction=0.5):
    """One dict per particle with geometry in um / um^2 and colour statistics.

    Pass the difference map from segment() so perimeters follow the sub-pixel edge.
    """
    rows = []
    on_line = grid_band(labels.shape, px_per_square, 0)  # pixels on a printed square edge
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
        level = edge_level(mask, diff, edge_fraction) if diff is not None else None
        perim, outline_area = _polygon_length_area(subpixel_outline(mask, diff, level))
        perim_ij = perimeter_imagej(mask)
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
            "perimeter_imagej_um": perim_ij * u,
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
            "circularity": min(1.0, 4 * math.pi * outline_area / perim ** 2) if perim > 0 else float("nan"),
            "circularity_imagej": min(1.0, 4 * math.pi * area_px / perim_ij ** 2) if perim_ij > 0 else float("nan"),
            "solidity": min(1.0, area_px / convex_area) if convex_area > 0 else float("nan"),
        }
        row.update(_color_stats(img_bgr, mask))
        # Used for review flags (export.py), not written to the CSV.
        row["_contrast"] = level / edge_fraction if level is not None else float("nan")
        row["_touches_gridline"] = bool((mask & on_line).any())
        rows.append(row)
    return rows
