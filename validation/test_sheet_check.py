"""The sheet check end to end, on synthetic sheet photos whose answers are known."""
import csv

import cv2
import pytest

from mippr.capture.sheet import Layout
from mippr.capture.synthetic import draw_particle, photograph, sheet_bgr

import sheet_check
from lab_sheets import lab_color, lab_shape, normalise_id, read_lab_records

DPI = 300

# (photo, background, box, shape, size mm, BGR, extra drawing args, lab row: id, shape, colour, length um, width um)
PLACED = [
    ("white.jpg", "white_grid", "B2", "disc", 2.0, (40, 40, 200), {}, ("W05", "Fragment", "Red", 2400, 2400)),
    # a rectangle's longest distance across (max Feret) is its diagonal: 4 x 2 mm -> 4.47 mm
    ("white.jpg", "white_grid", "D3", "rect", 4.0, (60, 160, 60), {"aspect": 2}, ("W06", "Fragment", "Green", 4472, 2000)),
    ("white.jpg", "white_grid", "F7", "rect", 9.0, (200, 120, 40), {"aspect": 12, "angle": 10},
     ("F01", "Fiber", "Blue", 9000, 750)),
    ("white.jpg", "white_grid", "H5", "disc", 3.0, (25, 25, 25), {}, ("W07", "Rubbery Fragment", "Black", 3000, 3000)),
    ("black.jpg", "black_grid", "C4", "disc", 2.5, (235, 235, 235), {}, ("W08", "Fragment", "White", 2500, 2500)),
    ("black.jpg", "black_grid", "E6", "rect", 3.0, (40, 40, 200), {"aspect": 1.5}, ("W09", "Fragment", "Red", 3606, 2000)),
]
NOT_LISTED = ("white.jpg", "white_grid", "E10", "disc", 2.0, (40, 40, 200))  # drawn but not on the list: extra
EMPTY_LISTED = ("white.jpg", "C8", "W10")  # on the list but nothing placed: missed


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    d = tmp_path_factory.mktemp("sheet_check")
    photos = d / "photos"
    photos.mkdir()
    for name, bg in (("white.jpg", "white_grid"), ("black.jpg", "black_grid")):
        lay = Layout(bg, "letter")
        img = sheet_bgr(lay, DPI)
        for p in PLACED:
            if p[0] == name:
                draw_particle(img, lay, DPI, p[2], p[3], p[4], p[5], **p[6])
        if name == NOT_LISTED[0]:
            draw_particle(img, lay, DPI, *NOT_LISTED[2:])
        cv2.imwrite(str(photos / name), photograph(img, seed=3, k1=-0.02))
    with open(d / "boxes.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["photo", "box", "sample_id", "particle_id", "note"])
        for p in PLACED:
            w.writerow([p[0], p[2], "S1", p[7][0], ""])
        w.writerow([EMPTY_LISTED[0], EMPTY_LISTED[1], "S1", EMPTY_LISTED[2], ""])
    with open(d / "lab.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["SampleID", "ParticleID", "ParticleShape", "ParticleColor", "ParticleLength", "ParticleWidth"])
        for p in PLACED:
            w.writerow(["S1", *p[7]])
        w.writerow(["S1", "W10", "Fragment", "Blue", 1500, 1000])
    with open(d / "calipers.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["sample_id", "particle_id", "length_mm", "width_mm"])
        w.writerow(["S1", "W05", 2.0, 2.0])  # the spreadsheet says 2.4: the calipers decide
    out = d / "out"
    recs = sheet_check.main(["--photos", str(photos), "--boxes", str(d / "boxes.csv"), "--lab", str(d / "lab.csv"),
                             "--calipers", str(d / "calipers.csv"), "--out", str(out)])
    return {(r["photo"], r["box"]): r for r in recs}, out


def test_lab_names_map_to_app_classes():
    assert lab_shape("Rubbery Fragment") == "rubbery_fragment" and lab_shape("Line Bundle") == "fiber"
    assert lab_shape("Sphere") == "pellet" and lab_shape("Something else") is None
    assert lab_color("Multicolor (2+ colors)") == "multicolor" and lab_color("Unknown") is None
    assert lab_color("Black") == "black"
    assert normalise_id("w5") == "W05" and normalise_id("F3") == "F03" and normalise_id("P01") == "P01"


def test_lab_sheet_reader(tmp_path):
    p = tmp_path / "s.csv"
    p.write_text("SampleID,ParticleID,ParticleShape,ParticleColor,ParticleLength,ParticleWidth,Notes\n"
                 "S1,W5,Fiber,Blue,6085.9,59.3,\nS1,W06,Fragment,White,,,Particle Missing\n")
    rec = read_lab_records(p)
    assert rec[("S1", "W05")]["length_mm"] == pytest.approx(6.0859)
    assert rec[("S1", "W05")]["shape_class"] == "fiber"
    assert rec[("S1", "W06")]["length_mm"] is None and rec[("S1", "W06")]["notes"] == "Particle Missing"


def test_missed_and_extra_are_counted(run):
    recs, _ = run
    assert recs[("white.jpg", "C8")]["status"] == "missed"
    assert recs[("white.jpg", "E10")]["status"] == "extra"
    assert all(recs[(p[0], p[2])]["status"] in ("matched", "multi_blob") for p in PLACED)


def test_calipers_are_the_size_reference_where_measured(run):
    recs, _ = run
    b2 = recs[("white.jpg", "B2")]
    assert b2["size_reference"] == "calipers"
    assert abs(b2["length_error"]) < SIZE_TOLERANCE  # the app agrees with the calipers ...
    assert b2["lab_vs_caliper_length"] == pytest.approx(0.2)  # ... and the spreadsheet was 20% off
    assert recs[("white.jpg", "D3")]["size_reference"] == "lab"


# Max Feret over pixel corners (ImageJ's convention) reads about 1.25 px long, plus about 1 px from this
# synthetic photo's rendering and blur: at about 10 px/mm that is up to +12% on a 2-3 mm particle.
SIZE_TOLERANCE = 0.15


@pytest.mark.parametrize("key", [("white.jpg", "D3"), ("white.jpg", "H5"), ("black.jpg", "C4"), ("black.jpg", "E6")])
def test_sizes_agree_with_the_known_answer(run, key):
    assert abs(run[0][key]["length_error"]) < SIZE_TOLERANCE


def test_colour_and_morphology_are_compared_with_the_lab(run):
    recs, _ = run
    assert recs[("white.jpg", "B2")]["color_correct"] is True
    assert recs[("black.jpg", "C4")]["app_color"] == "white" and recs[("black.jpg", "C4")]["color_correct"] is True
    assert recs[("white.jpg", "F7")]["app_morphology"] == "fiber" and recs[("white.jpg", "F7")]["morphology_correct"]
    # rubbery fragment needs the v3 model: the rules say fragment, which counts as a disagreement
    assert recs[("white.jpg", "H5")]["lab_shape_class"] == "rubbery_fragment"
    assert recs[("white.jpg", "H5")]["morphology_correct"] is False


def test_report_and_csv_are_written(run):
    _, out = run
    text = (out / "report.md").read_text()
    for heading in ("## Detection", "## Size", "## Colour", "## Morphology", "## Which flags catch wrong sizes",
                    "`size_uncertainty` thresholds"):
        assert heading in text
    rows = list(csv.DictReader(open(out / "particles.csv")))
    assert len(rows) == len(PLACED) + 2 and (out / "photos" / "white" / "overlay.png").exists()
