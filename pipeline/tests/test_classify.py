"""Spec v0.3 measurements and rules: fiber length along the fiber, opacity, colour classes, morphology rules."""
import math

import cv2
import numpy as np
import pytest

from mippr.color.rules import color_classes
from mippr.measurement.fiber import fiber_metrics
from mippr.measurement.opacity import opacity
from mippr.morphology.rules import morphology_rules


def _arc_mask(radius=150, width=6, sweep_deg=120, size=400):
    m = np.zeros((size, size), np.uint8)
    cv2.ellipse(m, (size // 2, size // 2 + radius // 2), (radius, radius), 0, -90 - sweep_deg / 2,
                -90 + sweep_deg / 2, 1, width)
    return m.astype(bool)


def test_curved_fiber_length_follows_the_fiber():
    radius, width, sweep = 150, 6, 120
    mask = _arc_mask(radius, width, sweep)
    true_len = math.radians(sweep) * radius + width  # centre-line arc plus the two rounded ends
    length, w, uniform = fiber_metrics(mask)
    assert uniform
    assert abs(length - true_len) / true_len < 0.05
    assert abs(w - width) < 1.5
    chord = 2 * radius * math.sin(math.radians(sweep / 2)) + width
    assert chord < 0.9 * true_len  # max Feret alone would read about 17% short here


def test_straight_rectangle_length_and_width():
    m = np.zeros((100, 300), bool)
    m[40:52, 20:260] = True  # 240 x 12 px
    length, w, uniform = fiber_metrics(m)
    assert abs(length - 240) < 6 and abs(w - 12) < 1.5 and uniform


@pytest.mark.parametrize("size,angle", [((60, 30), 0), ((60, 30), 30), ((90, 30), 0), ((240, 12), 30)])
def test_square_ended_pieces_are_not_lengthened_by_their_corners(size, angle):
    m = np.zeros((400, 400), np.uint8)
    cv2.fillPoly(m, [np.round(cv2.boxPoints(((200, 200), size, angle))).astype(np.int32)], 1)
    length, w, _ = fiber_metrics(m.astype(bool))
    assert abs(length / w - size[0] / size[1]) / (size[0] / size[1]) < 0.1


def test_a_compact_blob_does_not_look_like_a_fiber():
    m = np.zeros((200, 200), np.uint8)
    cv2.ellipse(m, (100, 100), (60, 40), 20, 0, 360, 1, -1)
    length, w, _ = fiber_metrics(m.astype(bool))
    assert length / w < 2.5


def _disc(img, centre, r, colour):
    cv2.circle(img, centre, r, colour, -1)
    m = np.zeros(img.shape[:2], np.uint8)
    cv2.circle(m, centre, r, 1, -1)
    return m.astype(bool)


@pytest.mark.parametrize("bgr,name", [((40, 40, 200), "red"), ((200, 80, 30), "blue"), ((60, 160, 60), "green"),
                                      ((245, 245, 245), "white"), ((20, 20, 20), "black"),
                                      ((30, 140, 240), "orange"), ((40, 220, 230), "yellow")])
def test_single_colours(bgr, name):
    img = np.full((120, 120, 3), 128, np.uint8)
    m = _disc(img, (60, 60), 30, bgr)
    label, conf, _, _ = color_classes(img, m)
    assert label == name and conf > 0.9


def test_two_colour_particle_is_multicolor_and_keeps_its_second_colour():
    img = np.full((120, 120, 3), 128, np.uint8)
    m = _disc(img, (60, 60), 30, (200, 80, 30))  # blue
    img[60:, :][m[60:, :]] = (40, 40, 200)  # bottom half red
    label, _, second, share = color_classes(img, m)
    assert label == "multicolor" and second in ("red", "blue") and 0.35 < share < 0.6


def test_small_second_colour_is_recorded_but_not_multicolor():
    img = np.full((120, 120, 3), 128, np.uint8)
    m = _disc(img, (60, 60), 30, (200, 80, 30))  # blue
    img[78:, :][m[78:, :]] = (40, 40, 200)  # a red strip, about 10%
    label, _, second, share = color_classes(img, m)
    assert label == "blue" and second == "red" and 0.03 < share < 0.2


def test_shading_does_not_make_a_particle_multicolor():
    img = np.full((120, 120, 3), 0, np.uint8)
    m = _disc(img, (60, 60), 30, (235, 235, 235))
    img[60:, :][m[60:, :]] = (170, 170, 170)  # the lower half in shadow: white + grey
    label, _, second, _ = color_classes(img, m)
    assert label in ("white", "grey") and second in ("white", "grey") and label != "multicolor"


def test_opacity_on_a_dark_box():
    bg = np.full((120, 120, 3), 15, np.uint8)
    img = bg.copy()
    m = _disc(img, (60, 60), 30, (240, 240, 240))
    assert opacity(img, bg, m) > 0.9  # an opaque white particle
    img2 = bg.copy()
    img2[m] = (0.3 * 240 + 0.7 * 15,) * 3  # 30% opaque, 70% of the black shows through
    assert abs(opacity(img2, bg, m) - 0.3) < 0.05


def test_clear_particle_across_a_checkerboard_edge_is_measured_directly():
    bg = np.zeros((120, 120, 3), np.uint8)
    bg[:, 60:] = 235  # left half black box, right half white box
    a = 0.25
    img = (a * 200 + (1 - a) * bg.astype(np.float64)).astype(np.uint8)  # a pale particle 25% opaque
    m = np.zeros((120, 120), bool)
    cv2.circle(m.view(np.uint8), (60, 60), 30, 1, -1)
    img[~m] = bg[~m]
    assert abs(opacity(img, bg, m) - a) < 0.05


def test_clear_colour_label():
    bg = np.full((120, 120, 3), 15, np.uint8)
    img = bg.copy()
    m = _disc(img, (60, 60), 30, (80, 80, 80))  # grey-looking because the black shows through
    op = opacity(img, bg, m)
    assert op < 0.5
    assert color_classes(img, m, op)[0] == "clear"


def test_morphology_rules():
    assert morphology_rules(8.0, 0.3, 0.9, 1.0)[0] == "fiber"
    assert morphology_rules(1.05, 0.95, 0.99, 1.0)[0] == "pellet"
    assert morphology_rules(1.6, 0.7, 0.9, 0.2)[0] == "film"
    label, conf, runner, _ = morphology_rules(1.6, 0.7, 0.85, 0.95)
    assert label == "fragment" and conf == 0.5  # the rules can't refine an ordinary piece
    assert morphology_rules(1.5, 0.5, 0.9, None, width_unresolved=True)[0] == "fiber"
    assert morphology_rules(12.0, 0.2, 0.9, 0.2)[0] == "fiber"  # a see-through fiber is still a fiber


def test_grid_run_labels_a_curved_fiber_and_sizes_it_along_the_fiber(tmp_path):
    import csv

    from mippr.cli import run_grid
    from mippr.capture.sheet import Layout
    from mippr.capture.synthetic import photograph, sheet_bgr

    dpi = 300
    lay = Layout("white_grid", "letter")
    img = sheet_bgr(lay, dpi)
    ppm = dpi / 25.4
    gx, gy = lay.grid_origin_mm
    # A curved blue fiber in box C4: 5.5 mm along its centre line, 0.35 mm wide.
    cx, cy = (gx + 3.5 * lay.box_mm) * ppm, (gy + 2.6 * lay.box_mm) * ppm
    r = 3.5 * ppm
    cv2.ellipse(img, (int(cx), int(cy + r * 0.6)), (int(r), int(r)), 0, -135, -45, (200, 90, 30),
                int(round(0.35 * ppm)), cv2.LINE_AA)
    # A round red pellet in box F7.
    cv2.circle(img, (int((gx + 6.5 * lay.box_mm) * ppm), int((gy + 5.5 * lay.box_mm) * ppm)), int(1.2 * ppm),
               (40, 40, 200), -1, cv2.LINE_AA)
    photo = photograph(img, seed=4, k1=-0.02, out_width=3000)
    p = tmp_path / "photo.jpg"
    cv2.imwrite(str(p), photo)
    run_grid(p, tmp_path / "out", "S1")
    rows = {r["particle_id"]: r for r in csv.DictReader(open(tmp_path / "out" / "particles.csv"))}
    fiber, pellet = rows["C4"], rows["F7"]
    assert fiber["morphology_label"] == "fiber" and fiber["size_length_source"] == "fiber_length"
    true_len = math.radians(90) * 3.5 + 0.35
    assert abs(float(fiber["fiber_length_mm"]) - true_len) / true_len < 0.08
    assert float(fiber["fiber_length_mm"]) > float(fiber["length_mm"])
    assert fiber["color_label"] == "blue"
    assert pellet["morphology_label"] == "pellet" and pellet["color_label"] == "red"
    assert float(pellet["opacity"]) > 0.8 and pellet["fiber_length_mm"] == ""


def test_extreme_shapes_do_not_break_the_rules():
    assert morphology_rules(500.0, 0.01, 0.2, 0.9)[0] == "fiber"  # a very long thin line
    assert morphology_rules(float("nan"), float("nan"), 0.9, None)[0] == "fragment"
