"""Tests on a synthetic photo: a known board, known particles, a perspective tilt
and a different exposure between the particle and template shots."""
import math

import cv2
import numpy as np
import pytest

from mippr.capture.board import SQUARES_X, SQUARES_Y, find_board
from mippr.measurement.geometry import feret, measure, perimeter_imagej, well_id
from mippr.segmentation.legacy import segment

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
    ("circle", (0.05, 15.5), 11, (60, 200, 230)),  # yellow disc cut off by the board's left edge
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


def test_edge_particle_is_kept_and_flagged(scene):
    _, _, rows = scene
    from mippr.export import flags
    row = nearest(rows, *PARTICLES[4][1])
    assert row["_touches_edge"]
    assert flags(row)["flag_edge"] is True
    assert sum(r["_touches_edge"] for r in rows) == 1


def _m(**kw):
    base = dict(particle=1, box="A1", x_um=0.0, y_um=0.0, feret_max_um=2000.0, feret_min_um=1500.0,
                area_um2=3e6, perimeter_um=7000.0, ced_um=1950.0, convex_area_um2=3.1e6,
                convex_perimeter_um=6900.0, aspect_ratio=1.33, circularity=0.8, solidity=0.95,
                perimeter_imagej_um=7100.0, circularity_imagej=0.78,
                R_mean=200.0, G_mean=40.0, B_mean=40.0, L_mean=45.0, a_mean=60.0, b_mean=40.0,
                L_sd=3.0, a_sd=2.0, b_sd=2.0,
                _contrast=200.0, _touches_edge=False, _touches_line=False, _px={"cx": 10.0, "cy": 20.0, "x": 5, "y": 15, "w": 10, "h": 10})
    base.update(kw)
    return base


def test_flags():
    from mippr.export import flags
    on = lambda m, med=None: sorted(k for k, v in flags(m, med).items() if v is True)  # noqa: E731
    assert on(_m()) == []
    assert on(_m(feret_max_um=520, feret_min_um=400)) == ["flag_min_width", "flag_near_cutoff"]
    assert on(_m(_contrast=90)) == ["flag_low_contrast"]
    assert on(_m(solidity=0.6)) == ["flag_merged"]
    assert on(_m(area_um2=10e6), med=3.0) == ["flag_merged"]  # more than 3x the image's median area
    assert on(_m(_touches_edge=True)) == ["flag_edge"]
    assert flags(_m())["flag_low_confidence"] == ""  # not available before colour rules / the model


def test_rows_and_summary_follow_output_csv():
    from mippr.export import COLUMNS, SUMMARY_COLUMNS, build_rows, build_summary
    ms = [_m(particle=1, box="A1"), _m(particle=2, box="B3", feret_max_um=6000.0),
          _m(particle=3, box="C2", feret_min_um=300.0)]
    rows = build_rows(ms, "S042", "S042-P01", "photo-1a2b3c4d", {"operator": "DS"}, "0.1.0", 0.0714,
                      "2026-11-02T00:00:00+00:00")
    assert all(list(r) == COLUMNS for r in rows)
    r = rows[0]
    assert (r["particle_id"], r["particle_ref"], r["image_id"]) == ("A1", "S042-P01-A1", "photo-1a2b3c4d")
    assert (r["length_mm"], r["area_mm2"]) == (2.0, 3.0)
    assert r["size_class"] == "2-5" and rows[1]["size_class"] == ">5"
    assert r["color_hex"] == "#c82828"
    assert r["review_status"] == "auto" and r["outline_edited"] is False and r["operator"] == "DS"
    assert rows[2]["review_reason"] == "min_width"
    assert r["polymer_confirmed"] == "" and r["color_label"] == ""  # no colour classes in this fake measurement
    # Morphology comes from the v2 rules: an ordinary piece is a fragment the rules can't refine (0.5)
    assert (r["morphology_label"], r["morphology_source"], r["morphology_confidence"]) == ("fragment", "rule", 0.5)

    rows[1]["review_status"] = "rejected"
    rows[2]["review_status"] = "corrected"
    (s,) = build_summary(rows)
    assert list(s) == SUMMARY_COLUMNS
    assert s["n_particles"] == 2 and s["count_size_>5"] == 0  # the rejected row is left out
    assert s["n_reviewed"] == 2 and s["n_corrected"] == 1 and s["pct_human_confirmed"] == 50.0
    assert s["n_flag_min_width"] == 1
    assert s["count_fragment"] == 2 and s["count_fiber"] == 0  # rule labels are counted
    assert s["count_color_red"] == ""  # no colour labels in this fake measurement, so no counts


def test_two_blobs_in_a_box_get_numbered_ids_and_a_flag():
    from mippr.export import build_rows
    ms = [_m(particle=1, box="B4", x_um=500.0, y_um=100.0), _m(particle=2, box="B4", x_um=100.0, y_um=100.0),
          _m(particle=3, box="C1")]
    rows = build_rows(ms, "S1", "S1-P02", "img", {}, "0.1.0", 0.1, "t")
    got = {r["particle_ref"]: r["flag_multi_blob"] for r in rows}
    assert got == {"S1-P02-B4-2": True, "S1-P02-B4-1": True, "S1-P02-C1": False}  # numbered left to right


def test_merged_area_rule_can_be_turned_off():
    from mippr.export import build_rows
    ms = [_m(particle=i, box=f"A{i}") for i in range(1, 4)] + [_m(particle=4, box="A4", area_um2=20e6)]
    on = build_rows(ms, "S", "S-P01", "img", {}, "v", 0.1, "t")
    off = build_rows(ms, "S", "S-P01", "img", {}, "v", 0.1, "t", merged_area_rule=False)
    assert on[3]["flag_merged"] is True and off[3]["flag_merged"] is False
