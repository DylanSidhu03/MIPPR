"""Part 6: applying review decisions, re-measuring edited outlines and the review order."""
import math

import cv2
import numpy as np
import pytest

from mippr.capture.calibration import white_balance
from mippr.capture.sheet import Layout, find_sheet
from mippr.capture.synthetic import draw_particle, photograph, sheet_bgr
from mippr.cli import run_grid
from mippr.export import COLUMNS, build_rows, build_summary
from mippr.measurement.geometry import measure
from mippr.review.corrections import (REMEASURED, Decision, MeasureContext, apply, apply_all, kept,
                                      review_queue)
from mippr.segmentation.grid import GridSegmentParams, background_image, box_of, line_band, segment_grid


def _m(**kw):
    m = {"particle": 1, "box": "A1", "x_um": 1000.0, "y_um": 1000.0, "area_um2": 3e6, "perimeter_um": 7000.0,
         "perimeter_imagej_um": 7100.0, "convex_area_um2": 3.1e6, "convex_perimeter_um": 6900.0,
         "feret_max_um": 2000.0, "feret_min_um": 1500.0, "ced_um": 1950.0, "aspect_ratio": 1.33,
         "circularity": 0.8, "circularity_imagej": 0.75, "solidity": 0.97, "fiber_length_um": 2000.0,
         "fiber_width_um": 1500.0, "fiber_uniform": False, "opacity": 0.9, "color_label": "red",
         "color_confidence": 0.9, "color_secondary": "", "color_secondary_fraction": 0.0,
         "L_mean": 40.0, "a_mean": 50.0, "b_mean": 30.0, "L_sd": 1.0, "a_sd": 1.0, "b_sd": 1.0,
         "R_mean": 200.0, "G_mean": 40.0, "B_mean": 40.0, "_contrast": 200.0,
         "_px": {"cx": 10.0, "cy": 10.0, "x": 5, "y": 5, "w": 10, "h": 10}}
    m.update(kw)
    return m


def _rows():
    ms = [_m(particle=1, box="A1"), _m(particle=2, box="B3", feret_max_um=6000.0),
          _m(particle=3, box="C2", feret_min_um=300.0, color_confidence=0.4)]
    return build_rows(ms, "S042", "S042-P01", "img", {}, "0.1.0", 0.07, "2026-11-02T00:00:00+00:00")


def _d(ref, action, at="2026-11-12T10:00:00Z", **kw):
    return Decision(ref, action, "DS", "expert", at, **kw)


def test_confirm_records_reviewer_and_does_not_change_the_input():
    row = _rows()[0]
    before = dict(row)
    out = apply(row, _d("S042-P01-A1", "confirm"))
    assert row == before
    assert out["review_status"] == "confirmed"
    assert (out["reviewed_by"], out["reviewer_role"], out["reviewed_at"]) == ("DS", "expert", "2026-11-12T10:00:00Z")
    assert list(out) == COLUMNS


def test_relabel_twice_keeps_the_first_original():
    row = _rows()[0]
    once = apply(row, _d("S042-P01-A1", "relabel", color_label="pink", morphology_label="film"))
    assert (once["color_label"], once["color_label_original"]) == ("pink", "red")
    assert (once["morphology_label"], once["morphology_label_original"]) == ("film", "fragment")
    assert once["review_status"] == "corrected"
    twice = apply(once, _d("S042-P01-A1", "relabel", color_label="orange"))
    assert (twice["color_label"], twice["color_label_original"]) == ("orange", "red")
    assert twice["morphology_label_original"] == "fragment"
    # Back to the prediction for colour: only the morphology correction remains.
    back = apply(twice, _d("S042-P01-A1", "relabel", color_label="red"))
    assert (back["color_label"], back["color_label_original"], back["review_status"]) == ("red", "", "corrected")
    # Relabel to what it already is counts as a confirmation.
    same = apply(_rows()[0], _d("S042-P01-A1", "relabel", color_label="red"))
    assert same["review_status"] == "confirmed" and same["color_label_original"] == ""


def test_confirm_after_a_correction_stays_corrected():
    row = apply(_rows()[0], _d("S042-P01-A1", "relabel", color_label="unknown"))
    assert apply(row, _d("S042-P01-A1", "confirm"))["review_status"] == "corrected"


def test_reject_then_summary_excludes():
    rows = _rows()
    out = apply_all(rows, [_d("S042-P01-B3", "reject")])
    assert [r["review_status"] for r in out] == ["auto", "rejected", "auto"]
    assert len(out) == 3 and len(kept(out)) == 2  # the rejected row stays in particles.csv
    (s,) = build_summary(out)
    assert s["n_particles"] == 2 and s["count_size_>5"] == 0 and s["n_reviewed"] == 1


def test_tags_set_and_update_review_reason():
    out = apply(_rows()[0], _d("S042-P01-A1", "tag", tags={"tar_like": True, "flag_bundle": True}))
    assert out["tar_like"] is True and out["flag_bundle"] is True
    assert out["review_reason"] == "bundle" and out["review_status"] == "auto"
    with pytest.raises(ValueError):
        apply(_rows()[0], _d("S042-P01-A1", "tag", tags={"sticky": True}))


@pytest.mark.parametrize("kw", [{"action": "delete"}, {"action": "relabel", "color_label": "teal"},
                                {"action": "relabel", "morphology_label": "blob"}, {"action": "relabel"},
                                {"action": "confirm", "role": "admin"}, {"action": "confirm", "at": "yesterday"},
                                {"action": "confirm", "particle_ref": "S042-P01-Z9"}])
def test_bad_decisions_raise(kw):
    d = {"particle_ref": "S042-P01-A1", "reviewer": "DS", "role": "expert", "at": "2026-11-12T10:00:00Z", **kw}
    with pytest.raises(ValueError):
        apply(_rows()[0], Decision(**d))


def test_unknown_action_raises():
    with pytest.raises(ValueError, match="Unknown review action"):
        apply(_rows()[0], _d("S042-P01-A1", "approve"))


def test_split_and_merge_are_not_built_yet():
    for action in ("split", "merge"):
        with pytest.raises(NotImplementedError):
            apply(_rows()[0], _d("S042-P01-A1", action))


def test_apply_all_uses_time_order():
    rows = _rows()
    ds = [_d("S042-P01-A1", "relabel", "2026-11-12T11:00:00Z", color_label="blue"),
          _d("S042-P01-A1", "relabel", "2026-11-12T10:00:00+00:00", color_label="pink")]
    (a, *_) = apply_all(rows, ds)
    assert (a["color_label"], a["color_label_original"], a["reviewed_at"]) == ("blue", "red", "2026-11-12T11:00:00Z")
    with pytest.raises(ValueError):
        apply_all(rows, [_d("S042-P01-Q1", "confirm")])


def test_review_queue_order():
    rows = _rows()  # A1 unflagged (conf 0.5 fragment), B3 unflagged, C2 flagged min_width
    rows[1]["review_status"] = "rejected"
    rows.append({**rows[0], "particle_ref": "S042-P01-D1", "review_status": "confirmed"})
    rows.append({**rows[0], "particle_ref": "S042-P01-E1", "color_confidence": "0.2"})  # as read from a CSV
    rows.append({**rows[0], "particle_ref": "S042-P01-F1", "review_reason": "edge"})
    order = [r["particle_ref"][-2:] for r in review_queue(rows)]
    assert order == ["C2", "F1", "E1", "A1", "D1", "B3"]


# --- Re-measuring an edited outline on the synthetic grid sample -----------------------------------

DPI = 300
SAMPLE = [("B2", "disc", 2.0, (40, 40, 200), (0, 0), {}),
          ("D3", "rect", 4.0, (60, 160, 60), (0, 0), {"aspect": 2}),
          ("F7", "rect", 9.0, (200, 120, 40), (2, 0), {"aspect": 12, "angle": 10}),
          ("K9", "disc", 0.6, (20, 180, 220), (0, 0), {}),
          ("H4", "disc", 1.2, (200, 200, 60), (-2.5, 0), {}), ("H4", "disc", 1.2, (200, 200, 60), (2.5, 0), {})]


@pytest.fixture(scope="module")
def grid_sample(tmp_path_factory):
    """The pipeline's rows for a synthetic black-grid photo, plus the labels and MeasureContext it measured with."""
    lay = Layout("black_grid", "letter")
    img = sheet_bgr(lay, DPI)
    for box, shape, size, col, off, kw in SAMPLE:
        draw_particle(img, lay, DPI, box, shape, size, col, offset_mm=off, **kw)
    photo = photograph(img, seed=3, k1=-0.03)
    path = tmp_path_factory.mktemp("review") / "photo.jpg"
    cv2.imwrite(str(path), photo)
    rows = run_grid(path, path.parent / "out", "S042", 3)
    # The same steps as cli.run_grid, kept here to build the context the review screen would hold.
    photo = cv2.imread(str(path))
    params = GridSegmentParams()
    sheet = find_sheet(photo)
    ppm = sheet.px_per_mm
    rect = sheet.rectify_grid(photo)
    gains, _ = white_balance(sheet, photo)
    balanced = np.clip(rect.astype(np.float32) * gains, 0, 255).astype(np.uint8)
    labels, diff, _ = segment_grid(rect, lay, ppm, params)
    band, _, outer = line_band(lay, ppm, labels.shape, params.line_margin_mm)
    near_line = cv2.dilate(band.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)
    ctx = MeasureContext(image=rect, mm_per_px=1.0 / ppm,
                         background=background_image(balanced, lay, ppm, params.inset_frac), diff=diff,
                         color_img=balanced, line_mask=near_line,
                         box_fn=lambda x, y: lay.box_label(*box_of(lay, ppm, x, y)),
                         edge_fraction=params.edge_fraction, edge_margin_px=int(np.ceil(outer)) + 2)
    measured = measure(labels, rect, ctx.mm_per_px * 1000, None, diff, ctx.edge_fraction,
                       edge_margin_px=ctx.edge_margin_px, box_fn=ctx.box_fn, line_mask=near_line,
                       color_img=balanced, bg_img=ctx.background)
    masks = {}
    for m in measured:
        ref = next(r["particle_ref"] for r in rows
                   if math.isclose(r["centroid_x_px"], round(m["_px"]["cx"], 1))
                   and math.isclose(r["centroid_y_px"], round(m["_px"]["cy"], 1)))
        masks[ref] = labels == m["particle"]
    return {r["particle_ref"]: r for r in rows}, masks, ctx


def _polygon(mask):
    contours, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    return max(contours, key=len).reshape(-1, 2).tolist()


def _same(a, b, cols):
    for c in cols:
        x, y = a[c], b[c]
        if isinstance(x, float) and math.isnan(x):
            assert isinstance(y, float) and math.isnan(y), c
        else:
            assert x == y, (c, x, y)


@pytest.mark.parametrize("ref", ["S042-P03-D3", "S042-P03-F7", "S042-P03-H4-1"])
def test_edit_outline_on_the_pipeline_mask_gives_the_pipeline_numbers(grid_sample, ref):
    rows, masks, ctx = grid_sample
    row = rows[ref]
    out = apply(row, _d(ref, "edit_outline", outline=_polygon(masks[ref])), ctx)
    _same(out, row, [c for c in REMEASURED if c != "app_version"])
    _same(out, row, ["particle_id", "review_reason", "flag_multi_blob", "processed_at"])
    assert out["outline_edited"] is True and out["review_status"] == "corrected"
    assert row["outline_edited"] is False  # the input is unchanged
    assert list(out) == COLUMNS


def test_edited_outline_is_remeasured_and_keeps_corrected_labels(grid_sample):
    rows, masks, ctx = grid_sample
    ref = "S042-P03-D3"
    relabelled = apply(rows[ref], _d(ref, "relabel", morphology_label="film"))
    half = masks[ref].copy()
    xs = np.nonzero(half.any(axis=0))[0]
    half[:, (xs.min() + xs.max()) // 2:] = False  # the reviewer cuts the outline in half
    out = apply(relabelled, _d(ref, "edit_outline", "2026-11-12T10:05:00Z", outline=_polygon(half)), ctx)
    assert out["area_mm2"] == pytest.approx(rows[ref]["area_mm2"] / 2, rel=0.05)
    assert out["morphology_label"] == "film" and out["morphology_label_original"] == rows[ref]["morphology_label"]
    assert out["color_label"] != "" and out["outline_edited"] is True


def test_edit_outline_needs_a_context(grid_sample):
    rows, masks, _ = grid_sample
    with pytest.raises(ValueError):
        apply(rows["S042-P03-D3"], _d("S042-P03-D3", "edit_outline", outline=_polygon(masks["S042-P03-D3"])))
