"""Printable grid backgrounds (Drive spec v0.6) and finding them in a photo.

Each sheet has a grid of square boxes, one particle per box, labelled by
row letter and column number in the margin (box B4 = row B, column 4).
Four ArUco markers in the corners give the scale and perspective, and their
IDs say which background and paper size was printed, so a photo needs no
other input. A 100 mm line checks printer scaling, and white and grey
patches give the white balance.

Everything is in mm on the sheet. `find_sheet` maps a photo back onto the
sheet at a chosen px per mm, first with a homography from the markers, then
by following the grid's own line crossings, which also corrects lens
distortion (the prototype found ~3 px of error with markers alone).
"""
import math
import string
from dataclasses import dataclass
from functools import cached_property

import cv2
import numpy as np

BACKGROUNDS = ("white_grid", "black_grid", "checkerboard")
PAPERS = {"letter": (215.9, 279.4), "a4": (210.0, 297.0)}
ARUCO_DICT = cv2.aruco.DICT_4X4_50
LAYOUT_VERSION = 1


@dataclass(frozen=True)
class Layout:
    """Geometry of one printable sheet, in mm from the top-left of the paper."""
    background: str = "white_grid"
    paper: str = "letter"
    box_mm: float = 12.0  # "around 10 mm or more"; particles in scope are 0.5-5 mm
    line_mm: float = 0.5  # "Standard" design, chosen November 5, 2026
    margin_mm: float = 8.0  # unprinted edge most printers need
    marker_mm: float = 18.0
    gap_mm: float = 8.0  # between the markers' inner edge and the grid, room for labels
    box_labels: bool = True  # also print each box's label (e.g. B4) small in its top-left corner
    label_zone_mm: tuple = (6.5, 3.2)  # top-left corner kept for the label: longest label (M12) prints 4.5 x 2 mm from 0.85 mm in

    def __post_init__(self):
        if self.background not in BACKGROUNDS:
            raise ValueError(f"background must be one of {BACKGROUNDS}")
        if self.paper not in PAPERS:
            raise ValueError(f"paper must be one of {tuple(PAPERS)}")

    @property
    def size_mm(self):
        return PAPERS[self.paper]

    @property
    def cols(self):
        w = self.size_mm[0] - 2 * (self.margin_mm + self.marker_mm + self.gap_mm)
        return int(w // self.box_mm)

    @property
    def rows(self):
        h = self.size_mm[1] - 2 * (self.margin_mm + self.marker_mm + self.gap_mm)
        return min(int(h // self.box_mm), 26)

    @property
    def grid_origin_mm(self):
        """Top-left corner of the grid, centred on the sheet."""
        w, h = self.size_mm
        return ((w - self.cols * self.box_mm) / 2, (h - self.rows * self.box_mm) / 2)

    @property
    def grid_size_mm(self):
        return self.cols * self.box_mm, self.rows * self.box_mm

    def marker_ids(self):
        """IDs for the top-left, top-right, bottom-right and bottom-left markers."""
        base = 4 * (BACKGROUNDS.index(self.background) * len(PAPERS) + list(PAPERS).index(self.paper))
        return [base + i for i in range(4)]

    def marker_corners_mm(self):
        """{marker id: 4x2 corners (TL, TR, BR, BL as OpenCV reports them)} in sheet mm."""
        w, h = self.size_mm
        m, s = self.margin_mm, self.marker_mm
        origins = [(m, m), (w - m - s, m), (w - m - s, h - m - s), (m, h - m - s)]
        return {i: np.array([[x, y], [x + s, y], [x + s, y + s], [x, y + s]], np.float64)
                for i, (x, y) in zip(self.marker_ids(), origins)}

    def box_label(self, row, col):
        return f"{string.ascii_uppercase[row]}{col + 1}"

    def scale_line_mm(self):
        """End points of the printed 100 mm check line, in the bottom margin."""
        w, h = self.size_mm
        y = h - self.margin_mm - self.marker_mm / 2
        return (w / 2 - 50, y), (w / 2 + 50, y)

    def patches_mm(self):
        """{name: (x, y, w, h, grey level 0-255)} white-balance patches in the top margin."""
        w = self.size_mm[0]
        y = self.margin_mm + 2
        return {"white": (w / 2 - 26, y, 24, 12, 255), "grey": (w / 2 + 2, y, 24, 12, 128)}


def layout_from_marker_ids(ids):
    """The Layout whose corner markers these IDs belong to (default box and line sizes)."""
    for bg in BACKGROUNDS:
        for paper in PAPERS:
            lay = Layout(bg, paper)
            if set(ids) & set(lay.marker_ids()):
                return lay
    raise ValueError("No MIPPR sheet markers found in the photo.")


# ── Drawing ────────────────────────────────────────────────────────────────

def render(layout, dpi=600):
    """The sheet as a grey image (uint8) at `dpi`."""
    ppm = dpi / 25.4
    w, h = (int(round(v * ppm)) for v in layout.size_mm)
    img = np.full((h, w), 255, np.uint8)
    p = lambda v: int(round(v * ppm))  # noqa: E731
    gx, gy = layout.grid_origin_mm
    b, lw = layout.box_mm, layout.line_mm
    gw, gh = layout.grid_size_mm

    if layout.background == "black_grid":
        img[p(gy):p(gy + gh), p(gx):p(gx + gw)] = 0
    if layout.background == "checkerboard":
        for r in range(layout.rows):
            for c in range(layout.cols):
                if (r + c) % 2:
                    img[p(gy + r * b):p(gy + (r + 1) * b), p(gx + c * b):p(gx + (c + 1) * b)] = 0
    if layout.background in ("white_grid", "black_grid"):
        ink = 0 if layout.background == "white_grid" else 255
        for c in range(layout.cols + 1):
            x = gx + c * b
            img[p(gy - lw / 2):p(gy + gh + lw / 2), p(x - lw / 2):p(x + lw / 2)] = ink
        for r in range(layout.rows + 1):
            y = gy + r * b
            img[p(y - lw / 2):p(y + lw / 2), p(gx - lw / 2):p(gx + gw + lw / 2)] = ink
    else:  # thin frame round the checkerboard so its outer edge is visible
        cv2.rectangle(img, (p(gx), p(gy)), (p(gx + gw), p(gy + gh)), 0, max(1, p(lw)))

    font = cv2.FONT_HERSHEY_SIMPLEX
    scale = 3.2 * ppm / 22  # text about 3 mm high
    thick = max(1, p(0.35))

    def text(s, cx, cy, size=1.0):
        (tw, th), _ = cv2.getTextSize(s, font, scale * size, thick)
        cv2.putText(img, s, (p(cx) - tw // 2, p(cy) + th // 2), font, scale * size, 0, thick, cv2.LINE_AA)

    for c in range(layout.cols):
        text(str(c + 1), gx + (c + 0.5) * b, gy - 3.5)
    for r in range(layout.rows):
        text(string.ascii_uppercase[r], gx - 3.5, gy + (r + 0.5) * b)
    if layout.box_labels:
        # Small grey label in each box's top-left corner; segmentation masks this known area like the lines.
        small = scale * 0.5
        sthick = max(1, p(0.18))
        for r in range(layout.rows):
            for c in range(layout.cols):
                dark_box = layout.background == "black_grid" or (layout.background == "checkerboard" and (r + c) % 2)
                ink = 150 if dark_box else 110
                cv2.putText(img, layout.box_label(r, c), (p(gx + c * b + lw + 0.6), p(gy + r * b + lw + 2.1)),
                            font, small, ink, sthick, cv2.LINE_AA)

    d = cv2.aruco.getPredefinedDictionary(ARUCO_DICT)
    for mid, pts in layout.marker_corners_mm().items():
        x0, y0 = pts[0]
        size = p(layout.marker_mm)
        img[p(y0):p(y0) + size, p(x0):p(x0) + size] = cv2.aruco.generateImageMarker(d, mid, size)

    (x0, y), (x1, _) = layout.scale_line_mm()
    cv2.line(img, (p(x0), p(y)), (p(x1), p(y)), 0, max(1, p(0.3)))
    for x in (x0, x1):
        cv2.line(img, (p(x), p(y - 2)), (p(x), p(y + 2)), 0, max(1, p(0.3)))
    text("100 mm: if this line is not 100 mm, enter its length in the app", (x0 + x1) / 2, y + 4.5, 0.6)

    for name, (x, y, pw, ph, level) in layout.patches_mm().items():
        img[p(y):p(y + ph), p(x):p(x + pw)] = level
        cv2.rectangle(img, (p(x), p(y)), (p(x + pw), p(y + ph)), 0, max(1, p(0.2)))
    w_mm = layout.size_mm[0]
    text(f"MIPPR {layout.background.replace('_', ' ')} | {layout.paper} | {layout.box_mm:g} mm boxes | "
         f"print at actual size (100%)", w_mm / 2, layout.margin_mm + 17, 0.55)
    return img


def save_sheet(layout, path_png, path_pdf=None, dpi=600):
    from PIL import Image
    img = Image.fromarray(render(layout, dpi))
    img.save(path_png, dpi=(dpi, dpi))
    if path_pdf:
        img.convert("L").save(path_pdf, "PDF", resolution=dpi)


# ── Finding the sheet in a photo ───────────────────────────────────────────

@dataclass
class Sheet:
    layout: Layout
    px_per_mm: float
    homography: np.ndarray  # photo -> sheet canvas (px_per_mm), from the markers
    crossings: np.ndarray  # (rows+1, cols+1, 2) grid crossings in photo px, refined
    markers_found: int

    @property
    def grid_size_px(self):
        gw, gh = self.layout.grid_size_mm
        return int(round(gw * self.px_per_mm)), int(round(gh * self.px_per_mm))

    @property
    def box_px(self):
        return self.layout.box_mm * self.px_per_mm

    def rectify_grid(self, img, interpolation=cv2.INTER_LINEAR):
        """The grid area only, flattened box by box: origin at the grid's top-left corner."""
        map_x, map_y = self._maps
        return cv2.remap(img, map_x, map_y, interpolation, borderMode=cv2.BORDER_REPLICATE)

    def rectify_sheet(self, img, interpolation=cv2.INTER_LINEAR):
        """The whole sheet from the marker homography (for margins: patches, scale line)."""
        w, h = (int(round(v * self.px_per_mm)) for v in self.layout.size_mm)
        return cv2.warpPerspective(img, self.homography, (w, h), flags=interpolation,
                                   borderMode=cv2.BORDER_REPLICATE)

    @cached_property
    def _maps(self):
        g = self.crossings.astype(np.float64)
        w, h = self.grid_size_px
        b = self.box_px
        rows, cols = self.layout.rows, self.layout.cols
        u = (np.arange(w) + 0.5) / b
        v = (np.arange(h) + 0.5) / b
        i0 = np.clip(np.floor(u).astype(int), 0, cols - 1)
        j0 = np.clip(np.floor(v).astype(int), 0, rows - 1)
        fu = (u - i0)[None, :, None]
        fv = (v - j0)[:, None, None]
        jj, ii = np.meshgrid(j0, i0, indexing="ij")
        top = g[jj, ii] * (1 - fu) + g[jj, ii + 1] * fu
        bot = g[jj + 1, ii] * (1 - fu) + g[jj + 1, ii + 1] * fu
        m = top * (1 - fv) + bot * fv - 0.5
        return m[..., 0].astype(np.float32), m[..., 1].astype(np.float32)

    def residual_mm(self):
        """How far the refined crossings moved from the marker-only homography (mean, mm)."""
        rows, cols = self.layout.rows, self.layout.cols
        gx, gy = self.layout.grid_origin_mm
        b = self.layout.box_mm
        ideal = np.stack(np.meshgrid(gx + np.arange(cols + 1) * b, gy + np.arange(rows + 1) * b), -1)
        warped = cv2.perspectiveTransform(self.crossings.reshape(-1, 1, 2), self.homography).reshape(ideal.shape)
        return float(np.linalg.norm(warped / self.px_per_mm - ideal, axis=-1).mean())


def detect_markers(img):
    gray = img if img.ndim == 2 else cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    det = cv2.aruco.ArucoDetector(cv2.aruco.getPredefinedDictionary(ARUCO_DICT), cv2.aruco.DetectorParameters())
    corners, ids, _ = det.detectMarkers(gray)
    if ids is None:
        return {}
    return {int(i): c.reshape(4, 2).astype(np.float64) for i, c in zip(ids.ravel(), corners)}


def find_sheet(img, px_per_mm=None, layout=None):
    """Locate a printed MIPPR sheet in a photo. Raises ValueError with a readable reason."""
    found = detect_markers(img)
    if layout is None:
        layout = layout_from_marker_ids(found)
    expected = layout.marker_corners_mm()
    found = {k: v for k, v in found.items() if k in expected}
    if len(found) < 2:
        raise ValueError(f"Found {len(found)} of the 4 corner markers; at least 2 are needed. "
                         "Is the whole sheet in the photo?")
    src = np.vstack([found[k] for k in sorted(found)])
    dst_mm = np.vstack([expected[k] for k in sorted(found)])
    if px_per_mm is None:
        # Keep about the photo's own resolution.
        side_px = np.mean([np.linalg.norm(c[1] - c[0]) for c in found.values()])
        px_per_mm = round(side_px / layout.marker_mm, 1)
    H, _ = cv2.findHomography(src, dst_mm * px_per_mm)
    crossings = _refine_crossings(img, layout, H, px_per_mm)
    return Sheet(layout, px_per_mm, H, crossings, len(found))


def _refine_crossings(img, layout, H, ppm):
    """Grid crossings in photo px, moved onto the printed lines (or checkerboard corners).

    The markers sit far out at the sheet corners, so with a distorting lens the
    marker-only estimate can miss the grid lines by up to about half a box.
    Pass 1 searches wide (just under half a box, so the nearest line is still
    unambiguous), a smooth surface is fitted to what it finds, and pass 2
    searches narrowly around that prediction.
    """
    gray = img if img.ndim == 2 else cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    w, h = (int(round(v * ppm)) for v in layout.size_mm)
    canvas = cv2.warpPerspective(gray, H, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    rows, cols, b = layout.rows, layout.cols, layout.box_mm * ppm
    gx, gy = (v * ppm for v in layout.grid_origin_mm)
    ideal = np.stack(np.meshgrid(gx + np.arange(cols + 1) * b, gy + np.arange(rows + 1) * b), -1)

    guess = np.zeros_like(ideal)
    for frac in (0.42, 0.25, 0.12):
        shift, ok = _search(canvas, layout, ideal, guess, int(max(4, frac * b)), b, ppm)
        guess = _smooth_fit(ideal, shift, ok)
    # Keep measured crossings that agree with the smooth surface; use the surface elsewhere.
    ok &= np.linalg.norm(shift - guess, axis=-1) < max(2.0, 0.03 * b)
    shift = np.where(ok[..., None], shift, guess)
    pts = (ideal + shift).reshape(-1, 1, 2)
    return cv2.perspectiveTransform(pts, np.linalg.inv(H)).reshape(rows + 1, cols + 1, 2)


def _search(canvas, layout, ideal, guess, half, b, ppm):
    """Find each crossing within `half` px of ideal + guess. Returns (shift from ideal, found)."""
    rows, cols = layout.rows, layout.cols
    shift = guess.copy()
    ok = np.zeros(ideal.shape[:2], bool)
    if layout.background == "checkerboard":
        start = (ideal + guess)[1:-1, 1:-1].reshape(-1, 1, 2).astype(np.float32)
        refined = cv2.cornerSubPix(canvas, start.copy(), (half, half), (-1, -1),
                                   (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 60, 0.01))
        d = (refined - start).reshape(rows - 1, cols - 1, 2)
        good = np.linalg.norm(d, axis=-1) < half
        shift[1:-1, 1:-1] += np.where(good[..., None], d, 0)
        ok[1:-1, 1:-1] = good
        return shift, ok
    line = ((255 - canvas) if layout.background == "white_grid" else canvas).astype(np.float32)
    lw = max(1.0, layout.line_mm * ppm)
    keep = np.abs(np.arange(-half, half + 1)) > 2 * lw + 2
    # On the black grid the outer border is a white line on white paper, so it can't be seen.
    inner_only = layout.background == "black_grid"
    for r in range(rows + 1):
        for c in range(cols + 1):
            if inner_only and (r in (0, rows) or c in (0, cols)):
                continue
            x0, y0 = ideal[r, c] + guess[r, c]
            xi, yi = int(round(x0)), int(round(y0))
            win = line[yi - half:yi + half + 1, xi - half:xi + half + 1]
            if win.shape != (2 * half + 1, 2 * half + 1):
                continue
            # Leave out the band of the crossing line, which is flat along the other axis.
            dx = _peak(win[keep, :].sum(axis=0), half)
            dy = _peak(win[:, keep].sum(axis=1), half)
            if dx is not None and dy is not None:
                shift[r, c] = guess[r, c] + (dx + (xi - x0), dy + (yi - y0))
                ok[r, c] = True
    return shift, ok


def _smooth_fit(ideal, shift, ok, degree=3):
    """Least-squares polynomial surface through the found shifts, with one round of outlier removal."""
    if ok.sum() < 10:
        return np.zeros_like(shift)
    span = ideal.reshape(-1, 2).max(axis=0)
    xy = ideal / span * 2 - 1
    terms = [(i, j) for i in range(degree + 1) for j in range(degree + 1 - i)]
    A = np.stack([xy[..., 0] ** i * xy[..., 1] ** j for i, j in terms], -1)
    mask = ok.copy()
    for _ in range(2):
        coef, *_ = np.linalg.lstsq(A[mask], shift[mask], rcond=None)
        fit = A @ coef
        err = np.linalg.norm(fit - shift, axis=-1)
        mask = ok & (err < max(2.0, 3 * np.median(err[ok])))
    return fit


def _peak(profile, half):
    """Sub-pixel offset of the profile's peak from the window centre, or None if there is no clear line."""
    p = profile - np.median(profile)
    k = int(np.argmax(p))
    if p[k] <= 0 or p[k] < 4 * (np.median(np.abs(p)) + 1e-6):
        return None
    lo, hi = max(0, k - 3), min(len(p), k + 4)
    wts = np.clip(p[lo:hi], 0, None)
    return float((np.arange(lo, hi) * wts).sum() / wts.sum()) - half
