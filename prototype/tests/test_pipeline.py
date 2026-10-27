"""Tests on a synthetic photo: a known board, known particles, a perspective tilt
and a different exposure between the particle and template shots."""
import math

import cv2
import numpy as np
import pytest

from mippr.board import SQUARES_X, SQUARES_Y, find_board
from mippr.measure import feret, measure, well_id
from mippr.segment import segment

SQ = 60  # px per square in the synthetic "photo" before tilting
MARGIN = 80
P = 60  # px per square after rectification
SQUARE_MM = 10.0
UM_PER_PX = SQUARE_MM * 1000 / P


def board_image(black=20, white=235):
    h, w = SQUARES_Y * SQ + 2 * MARGIN, SQUARES_X * SQ + 2 * MARGIN
    img = np.full((h, w, 3), white, np.uint8)
    for j in range(SQUARES_Y):
        for i in range(SQUARES_X):
            if (i + j) % 2:
                y, x = MARGIN + j * SQ, MARGIN + i * SQ
                img[y:y + SQ, x:x + SQ] = black
    return img


PARTICLES = [
    # (kind, centre in squares, size in px, BGR colour)
    ("circle", (2.5, 3.5), 12, (40, 40, 200)),  # red disc on a white or black square
    ("circle", (7.5, 10.5), 9, (230, 230, 230)),  # white disc
    ("rect", (5.5, 18.5), (30, 8), (60, 160, 60)),  # green elongated rectangle
    ("circle", (9.5, 6.0), 10, (200, 120, 40)),  # blue disc straddling a gridline
]


def add_particles(img):
    for kind, (cx, cy), size, color in PARTICLES:
        c = (int(MARGIN + cx * SQ), int(MARGIN + cy * SQ))
        if kind == "circle":
            cv2.circle(img, c, size, color, -1, cv2.LINE_AA)
        else:
            w, h = size
            cv2.rectangle(img, (c[0] - w // 2, c[1] - h // 2), (c[0] + w // 2 - 1, c[1] + h // 2 - 1), color, -1)
    return img


def tilt(img, seed):
    h, w = img.shape[:2]
    rng = np.random.default_rng(seed)
    src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    dst = src + rng.uniform(-25, 25, src.shape).astype(np.float32) + 40
    M = cv2.getPerspectiveTransform(src, dst)
    out = cv2.warpPerspective(img, M, (w + 80, h + 80), flags=cv2.INTER_LINEAR, borderValue=(120, 110, 100))
    return cv2.GaussianBlur(out, (0, 0), 0.8)


@pytest.fixture(scope="module")
def scene():
    template = tilt(board_image(black=8, white=230), seed=1)  # darker exposure, slightly different view
    particle = tilt(add_particles(board_image()), seed=2)
    rect_p = find_board(particle, P).rectify(particle)
    rect_t = find_board(template, P).rectify(template)
    labels, _ = segment(rect_p, rect_t, P)
    rows = measure(labels, rect_p, UM_PER_PX, P)
    return rect_p, labels, rows


def nearest(rows, cx, cy):
    return min(rows, key=lambda r: math.hypot(r["x_um"] / UM_PER_PX - cx * P, r["y_um"] / UM_PER_PX - cy * P))


def test_finds_every_particle_and_nothing_else(scene):
    _, _, rows = scene
    assert len(rows) == len(PARTICLES)


def test_rectified_board_is_aligned():
    img = tilt(board_image(), seed=3)
    rect = find_board(img, P).rectify(img)
    gray = cv2.cvtColor(rect, cv2.COLOR_BGR2GRAY)
    ok, c = cv2.findChessboardCorners(gray, (SQUARES_X - 1, SQUARES_Y - 1))
    assert ok
    c = np.sort(c.reshape(-1, 2), axis=0)
    xs, ys = np.meshgrid(np.arange(1, SQUARES_X) * P, np.arange(1, SQUARES_Y) * P)
    ideal = np.sort(np.stack([xs, ys], -1).reshape(-1, 2), axis=0)
    assert np.abs(c - ideal).max() < 1.5


@pytest.mark.parametrize("idx", [0, 1, 3])
def test_disc_size(scene, idx):
    _, _, rows = scene
    _, (cx, cy), r, _ = PARTICLES[idx]
    row = nearest(rows, cx, cy)
    true_d_um = (2 * r + 1) * SQUARE_MM * 1000 / SQ  # an antialiased cv2.circle spans 2r + 1 px
    assert row["ced_um"] == pytest.approx(true_d_um, rel=0.05)
    assert row["feret_max_um"] == pytest.approx(true_d_um, rel=0.08)
    assert row["circularity"] > 0.8


def test_rectangle_length_and_width(scene):
    _, _, rows = scene
    _, (cx, cy), (w, h), _ = PARTICLES[2]
    row = nearest(rows, cx, cy)
    scale = SQUARE_MM * 1000 / SQ
    assert row["feret_max_um"] == pytest.approx(math.hypot(w, h) * scale, rel=0.08)
    assert row["feret_min_um"] == pytest.approx(h * scale, rel=0.15)
    assert row["aspect_ratio"] > 3


def test_colour_of_red_disc(scene):
    _, _, rows = scene
    row = nearest(rows, *PARTICLES[0][1])
    assert row["R_mean"] > 150 and row["G_mean"] < 80 and row["B_mean"] < 80
    assert row["H_mean"] < 15 or row["H_mean"] > 345


def test_feret_of_unit_square():
    sq = np.array([[0, 0], [1, 0], [1, 1], [0, 1]], float)
    fmax, fmin, _ = feret(sq)
    assert fmax == pytest.approx(math.sqrt(2))
    assert fmin == pytest.approx(1)


def test_well_labels():
    assert well_id(0.5 * P, 0.5 * P, P) == "L1"  # top-left square
    assert well_id(11.5 * P, 0.5 * P, P) == "A1"  # top-right square
    assert well_id(11.5 * P, 23.5 * P, P) == "A12"
