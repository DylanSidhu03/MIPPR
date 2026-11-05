"""Printed grid sheets (Drive spec v0.6): generation, finding the sheet, per-box segmentation and export."""
import csv
import json

import cv2
import numpy as np
import pytest

from mippr.cli import run_grid
from mippr.grid import BACKGROUNDS, Layout, find_sheet, layout_from_marker_ids
from mippr.gridseg import box_of, segment_grid
from mippr.synthetic import draw_particle, photograph, sheet_bgr

DPI = 300

# (box, shape, size mm, BGR colour, offset mm, extra) chosen to contrast with every background
PARTICLES = [
    ("B2", "disc", 2.0, (40, 40, 200), (0, 0), {}),
    ("D3", "rect", 4.0, (60, 160, 60), (0, 0), {"aspect": 2}),
    ("F7", "rect", 9.0, (200, 120, 40), (2, 0), {"aspect": 12, "angle": 10}),  # fiber crossing into F8
    ("K9", "disc", 0.6, (20, 180, 220), (0, 0), {}),
]


def scene(background, extra=(), seed=2, k1=-0.03):
    lay = Layout(background, "letter")
    img = sheet_bgr(lay, DPI)
    for box, shape, size, col, off, kw in list(PARTICLES) + list(extra):
        draw_particle(img, lay, DPI, box, shape, size, col, offset_mm=off, **kw)
    return lay, photograph(img, seed=seed, k1=k1)


def found_boxes(lay, photo):
    sh = find_sheet(photo)
    rect = sh.rectify_grid(photo)
    labels, _, band = segment_grid(rect, lay, sh.px_per_mm)
    out = []
    for k in range(1, labels.max() + 1):
        ys, xs = np.nonzero(labels == k)
        out.append((lay.box_label(*box_of(lay, sh.px_per_mm, xs.mean(), ys.mean())), bool((band & (labels == k)).any())))
    return sorted(out)


def test_marker_ids_identify_background_and_paper():
    for bg in BACKGROUNDS:
        for paper in ("letter", "a4"):
            lay = Layout(bg, paper)
            assert layout_from_marker_ids(lay.marker_ids()[1:3]) == lay
    ids = [i for bg in BACKGROUNDS for p in ("letter", "a4") for i in Layout(bg, p).marker_ids()]
    assert len(set(ids)) == len(ids) and max(ids) < 50  # all distinct, inside the 4x4_50 dictionary


@pytest.mark.parametrize("background", BACKGROUNDS)
def test_sheet_is_flattened_to_a_fraction_of_a_pixel(background):
    """Strong barrel distortion and tilt; the grid's crossings must still land on the ideal grid."""
    lay = Layout(background, "letter")
    photo = photograph(sheet_bgr(lay, DPI), seed=1, k1=-0.04)
    sh = find_sheet(photo)
    assert sh.markers_found == 4
    rect = cv2.cvtColor(sh.rectify_grid(photo), cv2.COLOR_BGR2GRAY).astype(float)
    b = sh.box_px
    if background == "checkerboard":
        signal = np.abs(np.diff(rect, axis=1))  # box edges
        offset = 0.5
    else:
        signal = (255 - rect) if background == "white_grid" else rect  # printed lines
        signal = signal[:, :-1]
        offset = 0.0
    errs = []
    for c in range(1, lay.cols):
        x0 = int(round(c * b))
        for r in range(lay.rows):
            seg = signal[int((r + 0.25) * b):int((r + 0.75) * b), x0 - 8:x0 + 8].mean(axis=0)
            seg = seg - seg.min()
            errs.append((np.arange(x0 - 8, x0 + 8) + offset) @ seg / seg.sum() - c * b)
    errs = np.abs(errs)
    assert errs.mean() < 0.3 and errs.max() < 1.0


@pytest.mark.parametrize("background", BACKGROUNDS)
def test_one_particle_per_box_and_line_crossing(background):
    lay, photo = scene(background)
    got = found_boxes(lay, photo)
    assert [b for b, _ in got] == ["B2", "D3", "F7", "K9"]  # nothing from the printed lines or frame
    assert dict(got)["F7"] is True and dict(got)["B2"] is False  # only the fiber touches a line


def test_low_contrast_particle_is_missed_only_on_the_matching_background():
    white = [("C5", "disc", 3.0, (230, 230, 230), (0, 0), {})]
    assert "C5" in [b for b, _ in found_boxes(*scene("black_grid", white))]
    assert "C5" not in [b for b, _ in found_boxes(*scene("white_grid", white))]


def test_grid_run_writes_ids_flags_and_scale(tmp_path):
    extra = [("H4", "disc", 1.2, (200, 200, 60), (-2.5, 0), {}), ("H4", "disc", 1.2, (200, 200, 60), (2.5, 0), {}),
             ("A1", "disc", 2.0, (60, 200, 230), (-5.5, 0), {})]  # A1 is cut by the grid's outer edge
    _, photo = scene("black_grid", extra, seed=3)
    path = tmp_path / "photo.jpg"
    cv2.imwrite(str(path), photo)
    run_grid(path, tmp_path / "out", "S042", 3)
    rows = {r["particle_ref"]: r for r in csv.DictReader(open(tmp_path / "out" / "particles.csv"))}
    assert set(rows) == {"S042-P03-" + b for b in ("A1", "B2", "D3", "F7", "H4-1", "H4-2", "K9")}
    assert rows["S042-P03-A1"]["flag_edge"] == "True"
    assert rows["S042-P03-F7"]["flag_line"] == "True"
    assert rows["S042-P03-H4-1"]["flag_multi_blob"] == "True" and rows["S042-P03-B2"]["review_reason"] == ""
    assert rows["S042-P03-B2"]["background_type"] == "black_grid" and rows["S042-P03-B2"]["scale_source"] == "markers"
    # Size from the markers alone: the 2 mm disc (drawn 2.1 mm wide at 300 dpi) within ~0.15 mm.
    assert float(rows["S042-P03-B2"]["width_mm"]) == pytest.approx(2.1, abs=0.15)
    wb = json.load(open(tmp_path / "out" / "run.json"))["white_balance"]
    assert wb["grey_spread_after"] < 3


def test_printed_line_correction_scales_sizes(tmp_path):
    _, photo = scene("white_grid", seed=4)
    path = tmp_path / "p.jpg"
    cv2.imwrite(str(path), photo)
    a = {r["particle_id"]: r for r in run_grid(path, tmp_path / "a", "S", 1)}
    b = {r["particle_id"]: r for r in run_grid(path, tmp_path / "b", "S", 1, line_mm=98.0)}
    assert b["D3"]["length_mm"] == pytest.approx(a["D3"]["length_mm"] * 0.98)
    assert b["D3"]["flag_scale"] is True and b["D3"]["scale_source"] == "user_corrected"


def test_vector_pdf_is_well_formed():
    import re
    from mippr.grid import render_pdf
    for bg in ("white_grid", "black_grid", "checkerboard"):
        pdf = render_pdf(Layout(bg, "a4"))
        assert pdf.startswith(b"%PDF-1.4") and len(pdf) < 20000
        start = int(re.search(rb"startxref\n(\d+)", pdf).group(1))
        assert pdf[start:start + 4] == b"xref"
        for i, off in enumerate(re.findall(rb"(\d{10}) 00000 n", pdf), 1):
            assert pdf[int(off):].startswith(b"%d 0 obj" % i)
