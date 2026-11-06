"""Find the checkerboard in a photo and warp it to a flat, top-down grid.

The lab board is 12 squares wide and 24 tall, so it has 11 x 23 inner
corners. Warping every photo onto the same grid aligns a particle photo with
its empty-template photo, and fixes the scale: one square is always
``px_per_square`` pixels, so um per pixel = square size / px_per_square.
"""
from dataclasses import dataclass

import cv2
import numpy as np

SQUARES_X = 12
SQUARES_Y = 24
INNER = (SQUARES_X - 1, SQUARES_Y - 1)  # (11, 23) inner corners


@dataclass
class Board:
    corners: np.ndarray  # (23, 11, 2) inner corners in photo pixels, canonical order
    homography: np.ndarray  # photo -> rectified board, used only as a quality check
    px_per_square: int

    @property
    def size(self):
        return SQUARES_X * self.px_per_square, SQUARES_Y * self.px_per_square

    def rectify(self, img, interpolation=cv2.INTER_LINEAR):
        """Warp each square onto the grid using its own four corners.

        A single homography leaves a few pixels of error from lens distortion,
        which shows up as gridlines in the template difference. Interpolating
        between the detected corners follows the distortion instead.
        """
        map_x, map_y = self._maps()
        return cv2.remap(img, map_x, map_y, interpolation, borderMode=cv2.BORDER_REPLICATE)

    def _maps(self):
        p = self.px_per_square
        g = self.corners.astype(np.float64)
        # Extend the 11 x 23 inner grid by one row/column on each side so it
        # reaches the outer edge of the board.
        g = np.concatenate([2 * g[:1] - g[1:2], g, 2 * g[-1:] - g[-2:-1]], axis=0)
        g = np.concatenate([2 * g[:, :1] - g[:, 1:2], g, 2 * g[:, -1:] - g[:, -2:-1]], axis=1)
        w, h = self.size
        u = (np.arange(w) + 0.5) / p  # grid coordinate of each output pixel centre
        v = (np.arange(h) + 0.5) / p
        i0 = np.clip(np.floor(u).astype(int), 0, SQUARES_X - 1)
        j0 = np.clip(np.floor(v).astype(int), 0, SQUARES_Y - 1)
        fu = (u - i0)[None, :, None]
        fv = (v - j0)[:, None, None]
        jj, ii = np.meshgrid(j0, i0, indexing="ij")
        top = g[jj, ii] * (1 - fu) + g[jj, ii + 1] * fu
        bot = g[jj + 1, ii] * (1 - fu) + g[jj + 1, ii + 1] * fu
        m = top * (1 - fv) + bot * fv - 0.5
        return m[..., 0].astype(np.float32), m[..., 1].astype(np.float32)

    def homography_error_px(self):
        """Mean distance (rectified px) between homography-warped corners and the ideal grid.

        Large values mean strong lens distortion or a bent board.
        """
        pts = cv2.perspectiveTransform(self.corners.reshape(-1, 1, 2), self.homography)
        return float(np.linalg.norm(pts.reshape(-1, 2) - _ideal_grid(self.px_per_square), axis=1).mean())


def _ideal_grid(p):
    xs, ys = np.meshgrid(np.arange(1, SQUARES_X) * p, np.arange(1, SQUARES_Y) * p)
    return np.stack([xs, ys], axis=-1).reshape(-1, 2).astype(np.float32)


def _canonical_order(c):
    """Order corners so rows run left to right and top to bottom in the photo.

    A 12 x 24 board looks the same after a 180 degree turn, so the orientation
    closest to the photo's own is used. Photos must be taken with the board the
    same way up (labels readable) for well positions to mean anything.
    """
    c = c.reshape(INNER[1], INNER[0], 2)
    if (c[0, -1] - c[0, 0])[0] < 0 and (c[-1, 0] - c[0, 0])[1] < 0:
        c = c[::-1, ::-1]
    elif (c[0, -1] - c[0, 0])[0] < 0:
        c = c[:, ::-1]
    elif (c[-1, 0] - c[0, 0])[1] < 0:
        c = c[::-1, :]
    return np.ascontiguousarray(c)


def find_board(img, px_per_square=140, detect_width=1400):
    """Locate the board's inner corners and return a Board, or raise ValueError."""
    gray = img if img.ndim == 2 else cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    s = min(1.0, detect_width / max(gray.shape))
    small = cv2.resize(gray, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    flags = cv2.CALIB_CB_ADAPTIVE_THRESH | cv2.CALIB_CB_NORMALIZE_IMAGE
    ok, corners = cv2.findChessboardCorners(small, INNER, flags=flags)
    if not ok:
        raise ValueError("Could not find the 12 x 24 checkerboard. Is the whole board in frame?")
    corners = corners.reshape(-1, 2) / s
    # Refine at full resolution. Window is a fraction of one square.
    sq = np.linalg.norm(corners[1] - corners[0])
    win = max(3, int(sq / 8))
    corners = cv2.cornerSubPix(gray, corners.reshape(-1, 1, 2).astype(np.float32), (win, win), (-1, -1),
                               (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 50, 0.01))
    corners = _canonical_order(corners)
    H, _ = cv2.findHomography(corners.reshape(-1, 2), _ideal_grid(px_per_square))
    return Board(corners=corners, homography=H, px_per_square=px_per_square)
