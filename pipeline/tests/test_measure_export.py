"""Measurement geometry and the output rows, on shapes and measurements with known answers."""
import math

import numpy as np
import pytest

from mippr.measurement.geometry import feret, perimeter_imagej


def test_feret_of_unit_square():
    sq = np.array([[0, 0], [1, 0], [1, 1], [0, 1]], float)
    fmax, fmin, _ = feret(sq)
    assert fmax == pytest.approx(math.sqrt(2))
    assert fmin == pytest.approx(1)


def test_imagej_perimeter_matches_imagej():
    one = np.zeros((5, 5), bool)
    one[2, 2] = True
    assert perimeter_imagej(one) * 74.904 == pytest.approx(211.861, abs=0.001)  # value from the lab's ImageJ CSV
    rect = np.zeros((9, 9), bool)
    rect[2:6, 3:5] = True
    assert perimeter_imagej(rect) == pytest.approx(12 - 4 * (2 - math.sqrt(2)))  # every corner is cut when sides > 1 px


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
    on = lambda m: sorted(k for k, v in flags(m).items() if v is True)  # noqa: E731
    assert on(_m()) == []
    assert on(_m(feret_max_um=520, feret_min_um=400)) == ["flag_min_width", "flag_near_cutoff"]
    assert on(_m(_contrast=90)) == ["flag_low_contrast"]
    assert on(_m(solidity=0.6)) == ["flag_merged"]
    assert on(_m(_touches_edge=True)) == ["flag_edge"]
    assert flags(_m())["flag_low_confidence"] == ""  # not available before colour rules / the model


def test_rows_and_summary_follow_output_csv():
    from mippr.export import COLUMNS, SUMMARY_COLUMNS, build_rows, build_summary
    ms = [_m(particle=1, box="A1"), _m(particle=2, box="B3", feret_max_um=6000.0),
          _m(particle=3, box="C2", feret_min_um=300.0)]
    rows = build_rows(ms, "S042", "S042-P01", "photo-1a2b3c4d", {"operator": "DS"}, "0.1.0", 0.0714,
                      "2026-11-02T00:00:00+00:00", background_type="white_grid")
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
    rows = build_rows(ms, "S1", "S1-P02", "img", {}, "0.1.0", 0.1, "t", background_type="white_grid")
    got = {r["particle_ref"]: r["flag_multi_blob"] for r in rows}
    assert got == {"S1-P02-B4-2": True, "S1-P02-B4-1": True, "S1-P02-C1": False}  # numbered left to right
