"""Printer scale from the paper's edges (capture/calibration.py printer_scale)."""
import cv2
import pytest

from mippr.capture.calibration import lens_model, printer_problem, printer_scale
from mippr.capture.sheet import Layout, find_sheet
from mippr.capture.synthetic import draw_particle, photograph, printed, sheet_bgr
from mippr.cli import run_grid

DPI = 150


def shot(background="white_grid", paper="letter", scale=1.0, on=None, seed=1, particles=False):
    lay = Layout(background, paper)
    img = sheet_bgr(lay, DPI)
    if particles:
        draw_particle(img, lay, DPI, "B2", "disc", 3.0)
        draw_particle(img, lay, DPI, "F5", "rect", 4.0, aspect=2)
    return photograph(printed(img, lay, DPI, scale, on), seed=seed, out_width=2400)


def test_lens_model_recovers_the_distortion():
    p = shot()
    q, _, rms = lens_model(find_sheet(p), p)
    assert q == pytest.approx(-0.04, abs=0.002)  # synthetic.photograph's barrel distortion
    assert rms < 1.0


@pytest.mark.parametrize("background,paper,scale,on", [
    ("white_grid", "letter", 1.0, None),
    ("white_grid", "letter", 0.97, None),
    ("black_grid", "a4", 0.96, None),
    ("checkerboard", "a4", 0.94, "letter"),  # an A4 sheet fitted onto Letter paper
    ("black_grid", "letter", 1.0, "a4"),  # a Letter sheet on A4 paper at 100%: no scaling
    ("white_grid", "letter", 210 / 215.9, "a4"),  # a Letter sheet fitted onto A4: edges 13 mm out
])
def test_printer_scale(background, paper, scale, on):
    p = shot(background, paper, scale, on)
    ps = printer_scale(find_sheet(p), p)
    assert ps["paper"] == (on or paper)
    assert ps["scale"] == pytest.approx(scale, abs=0.002)
    if on is None and scale == 1.0:  # edges reported where the paper is, in sheet mm
        assert ps["edges_mm"]["left"] == pytest.approx(0, abs=0.08)
        assert ps["edges_mm"]["right"] == pytest.approx(215.9, abs=0.08)
    problem = printer_problem(ps)
    assert (problem is not None) == (abs(scale - 1) > 0.01)
    if problem:
        assert problem.code == "printer_scaled" and f"{100 * scale:.0f}%" in problem.message


def test_no_estimate_without_all_four_edges():
    p = shot(scale=0.97, seed=2)  # the top of the paper is out of the frame
    ps = printer_scale(find_sheet(p), p)
    assert ps["edges_mm"]["top"] is None and ps["scale"] is None
    assert printer_problem(ps) is None


def test_entered_line_length_wins():
    p = shot(scale=0.97)
    problem = printer_problem(printer_scale(find_sheet(p), p), line_mm=98.0)
    assert problem.code == "printer_scaled" and "entered length was used" in problem.message


def test_sizes_corrected_end_to_end(tmp_path):
    rows = {}
    for scale in (1.0, 0.97):
        path = tmp_path / f"p{scale}.png"
        cv2.imwrite(str(path), shot(scale=scale, particles=True))
        rows[scale] = {r["particle_id"]: r for r in run_grid(path, tmp_path / str(scale))}
    # Uncorrected, the 97% print measures the same as the 100% one (the markers shrink with it). Corrected,
    # it measures about 3% smaller; not exactly 3%, because the synthetic blur adds a fixed few pixels.
    for pid, r in rows[0.97].items():
        assert r["scale_source"] == "paper_edges" and r["flag_scale"] is True
        assert 0.965 < r["length_mm"] / rows[1.0][pid]["length_mm"] < 0.985
    assert all(r["scale_source"] == "markers" for r in rows[1.0].values())


def test_printer_check_command(tmp_path):
    from mippr.capture.printer_check import check
    path = tmp_path / "p97.png"
    cv2.imwrite(str(path), shot(scale=0.97))
    r = check(path, line_mm=97.2, out_dir=tmp_path / "out")
    assert r["paper"] == "letter" and r["missing_edges"] == []
    assert r["scale"] == pytest.approx(0.97, abs=0.002)
    assert r["difference_pct"] == pytest.approx(-0.2, abs=0.25)
    assert "97.0%" in r["verdict"] and cv2.imread(r["image"]) is not None
    cropped = tmp_path / "top_cut.png"
    cv2.imwrite(str(cropped), shot(scale=0.97, seed=2))  # the top edge is out of frame
    r = check(cropped)
    assert r["scale"] is None and "top" in r["verdict"]
