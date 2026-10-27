"""Tests on a synthetic photo: a known board, known particles, a perspective tilt
and a different exposure between the particle and template shots."""
import math

import cv2
import numpy as np
import pytest

from mippr.board import SQUARES_X, SQUARES_Y, find_board
from mippr.measure import feret, measure, perimeter_imagej, well_id
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
    labels, diff = segment(rect_p, rect_t, P)
    rows = measure(labels, rect_p, UM_PER_PX, P, diff)
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
    assert row["circularity"] > 0.93
    assert row["perimeter_um"] == pytest.approx(math.pi * true_d_um, rel=0.06)


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


def test_imagej_perimeter_matches_imagej():
    one = np.zeros((5, 5), bool)
    one[2, 2] = True
    assert perimeter_imagej(one) * 74.904 == pytest.approx(211.861, abs=0.001)  # value from the lab's ImageJ CSV
    rect = np.zeros((9, 9), bool)
    rect[2:6, 3:5] = True
    assert perimeter_imagej(rect) == pytest.approx(12 - 4 * (2 - math.sqrt(2)))  # every corner is cut when sides > 1 px


def _m(**kw):
    base = dict(particle=1, well="A1", x_um=0.0, y_um=0.0, feret_max_um=2000.0, feret_min_um=1500.0,
                solidity=0.95, _contrast=200.0, _touches_gridline=False)
    base.update(kw)
    return base


def test_review_reasons():
    from mippr.export import review_reasons
    assert review_reasons(_m()) == []
    assert review_reasons(_m(feret_max_um=520, feret_min_um=400)) == ["near_size_cutoff", "min_width_below_sieve"]
    assert review_reasons(_m(_contrast=90)) == ["low_contrast_outline"]
    assert review_reasons(_m(_touches_gridline=True, solidity=0.6)) == ["touches_gridline", "possibly_merged"]


def test_export_rows_follow_spec():
    from mippr.export import COLUMNS, build_rows
    rows = build_rows([_m(particle=1, well="A3", y_um=10), _m(particle=2, well="A3", y_um=5),
                       _m(particle=3, well="B1", feret_min_um=300)],
                      "S042", "photo.jpg", {"operator": "DS"}, "0.1.0", 10.0, 71.4)
    assert all(list(r) == COLUMNS for r in rows)
    ids = {r["particle_number"]: r["particle_id"] for r in rows}
    assert ids == {2: "S042-A3-1", 1: "S042-A3-2", 3: "S042-B1-1"}  # numbered top to bottom within a well
    flagged = {r["particle_id"]: (r["review"], r["review_reason"]) for r in rows}
    assert flagged["S042-B1-1"] == ("yes", "min_width_below_sieve")
    assert rows[0]["operator"] == "DS" and rows[0]["polymer_confirmed"] == "" and rows[0]["color_class"] == ""
