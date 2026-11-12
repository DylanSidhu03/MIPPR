"""Size uncertainty: how much the length moves when the edge is drawn at 40% and 60% of the contrast."""
import cv2
import numpy as np
import pytest

from mippr.export import SIZE_UNCERTAIN, flags, size_uncertainty
from mippr.measurement.geometry import measure
from mippr.segmentation.edges import fill_holes, hysteresis, refine_edges


def particle(contrast=200.0, blur=0.8, shape="ellipse", size=1.0):
    """One particle on a flat background, its difference map and its outline (as the pipeline draws it)."""
    bg = 230.0
    img = np.full((160, 160), bg, np.float32)
    canvas = np.zeros_like(img)
    if shape == "ellipse":
        cv2.ellipse(canvas, (80, 80), (int(40 * size), int(18 * size)), 25, 0, 360, 1.0, -1, cv2.LINE_AA)
    else:
        cv2.rectangle(canvas, (80 - int(30 * size), 80 - int(10 * size)), (80 + int(30 * size), 80 + int(10 * size)),
                      1.0, -1)
    img -= contrast * canvas
    img = cv2.GaussianBlur(img, (0, 0), blur)
    diff = np.clip(bg - img, 0, 255)
    band = np.zeros(diff.shape, bool)
    mask = refine_edges(fill_holes(hysteresis(diff, 0.12 * contrast, 0.3 * contrast, band)), diff, 0.5)
    bgr = cv2.cvtColor(np.clip(img, 0, 255).astype(np.uint8), cv2.COLOR_GRAY2BGR)
    (m,) = measure(mask.astype(np.int32), bgr, 50.0, diff)
    return m


def test_outer_edge_is_larger_and_inner_smaller():
    m = particle()
    assert m["length_um_inner"] <= m["feret_max_um"] <= m["length_um_outer"]
    assert m["width_um_inner"] <= m["feret_min_um"] <= m["width_um_outer"]


def test_sharp_particle_has_low_uncertainty_and_no_flag():
    m = particle(blur=0.8)
    assert size_uncertainty(m) < SIZE_UNCERTAIN
    assert flags(m)["flag_size_uncertain"] is False


@pytest.mark.parametrize("blur", [3.0, 5.0])
def test_blurred_particle_is_less_certain(blur):
    assert size_uncertainty(particle(blur=blur)) > size_uncertainty(particle(blur=0.8))


def test_small_blurred_particle_is_flagged():
    # The 40%-60% shift is about half the blur width at each end, so blur matters most on small particles
    m = particle(blur=4.0, size=0.35)
    assert flags(m)["flag_size_uncertain"] is True


def test_uncertainty_does_not_depend_on_contrast_alone():
    # A uniformly faint but sharp particle has a well-defined edge
    assert size_uncertainty(particle(contrast=40, blur=0.8)) < SIZE_UNCERTAIN


def test_no_edge_check_without_a_difference_map():
    mask = np.zeros((40, 40), np.int32)
    mask[10:30, 12:20] = 1
    (m,) = measure(mask, np.full((40, 40, 3), 128, np.uint8), 50.0)
    assert size_uncertainty(m) is None and flags(m)["flag_size_uncertain"] == ""
