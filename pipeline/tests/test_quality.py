"""Photo quality check (part 1): good synthetic photos pass, each kind of degraded photo fails with its own code."""
import json

import cv2
import numpy as np
import pytest

from mippr.capture.calibration import Problem, check_quality, measure_quality
from mippr.capture.sheet import BACKGROUNDS, Layout, detect_markers, find_sheet
from mippr.capture.synthetic import draw_particle, photograph, sheet_bgr
from mippr.cli import run_grid

DPI = 300


def good_photo(background, seed=2):
    """A sharp, evenly lit photo (about 11 px per mm), with paper exposed at about 200 rather than clipped."""
    lay = Layout(background, "letter")
    img = sheet_bgr(lay, DPI)
    draw_particle(img, lay, DPI, "B2", "disc", 2.0, (40, 40, 200))
    draw_particle(img, lay, DPI, "F7", "rect", 9.0, (200, 120, 40), offset_mm=(2, 0), aspect=12, angle=10)
    draw_particle(img, lay, DPI, "K9", "disc", 0.6, (20, 180, 220))
    img = (img.astype(np.float32) * 0.85).astype(np.uint8)
    return photograph(img, seed=seed, k1=-0.03)


def motion_blur(p, length):
    k = np.zeros((length, length), np.float32)
    k[length // 2, :] = 1.0 / length
    return cv2.filter2D(p, -1, k)


def glare_spot(p, radius_px=25):
    h, w = p.shape[:2]
    yy, xx = np.indices((h, w))
    spot = np.clip(1.5 - np.hypot(xx - w / 2, yy - h / 2) / radius_px, 0, 1)
    return np.clip(p.astype(np.float32) + 255 * spot[..., None], 0, 255).astype(np.uint8)


def shadow(p, depth=0.45):
    """The right half darkened, like the shadow of a phone held over the sheet."""
    w = p.shape[1]
    ramp = np.clip((np.arange(w) - 0.45 * w) / (0.1 * w), 0, 1)
    return (p.astype(np.float32) * (1 - (1 - depth) * ramp)[None, :, None]).astype(np.uint8)


def tinted(p):
    """Blue channel bent by a curve: white balance fixes white, but grey stays tinted."""
    q = p.astype(np.float32) / 255
    q[..., 0] **= 0.7
    return (q * 255).astype(np.uint8)


def cover_markers(p, which):
    q = p.copy()
    found = detect_markers(p)
    for i, (mid, c) in enumerate(sorted(found.items())):
        if i in which:
            (x0, y0), (x1, y1) = c.min(0).astype(int) - 10, c.max(0).astype(int) + 10
            q[y0:y1, x0:x1] = (60, 50, 40)  # a finger
    return q


def codes(p, use_sheet=True):
    sheet = None
    if use_sheet:
        try:
            sheet = find_sheet(p)
        except ValueError:
            pass
    return [q.code for q in check_quality(p, sheet)]


@pytest.fixture(scope="module")
def photos():
    return {bg: good_photo(bg) for bg in BACKGROUNDS}


@pytest.mark.parametrize("background", BACKGROUNDS)
def test_good_photos_pass(photos, background):
    assert codes(photos[background]) == []
    assert codes(good_photo(background, seed=5)) == []


DEGRADATIONS = {
    "blurry": lambda p: cv2.GaussianBlur(p, (0, 0), 2.0),
    "motion": lambda p: motion_blur(p, 7),
    "too_dark": lambda p: (p * 0.45).astype(np.uint8),
    "overexposed": lambda p: np.clip(p * 1.4, 0, 255).astype(np.uint8),
    "glare": glare_spot,
    "uneven_light": shadow,
    "color_cast": tinted,
    "marker_missing": lambda p: cover_markers(p, {1}),
    "low_resolution": lambda p: cv2.resize(p, None, fx=0.8, fy=0.8, interpolation=cv2.INTER_AREA),
}


@pytest.mark.parametrize("background", BACKGROUNDS)
@pytest.mark.parametrize("kind", DEGRADATIONS)
def test_each_degradation_gives_only_its_own_problem(photos, background, kind):
    if kind == "uneven_light" and background == "black_grid":
        pytest.skip("the black grid has no white boxes to compare")
    expected = "blurry" if kind == "motion" else kind
    assert codes(DEGRADATIONS[kind](photos[background])) == [expected]


def test_missing_marker_names_the_corner(photos):
    p = cover_markers(photos["white_grid"], {1, 2})  # sorted ids: TL, TR, BR, BL
    probs = check_quality(p, find_sheet(p))
    assert probs[0].code == "marker_missing" and probs[0].value == 2
    assert "top right" in probs[0].message and "bottom right" in probs[0].message


def test_without_the_sheet_the_other_checks_still_run(photos):
    p = cover_markers(photos["white_grid"], {0, 1, 2, 3})
    assert codes(p, use_sheet=False) == ["no_markers"]
    assert codes(cv2.GaussianBlur(p, (0, 0), 3.0), use_sheet=False) == ["no_markers", "blurry"]
    assert codes((p * 0.4).astype(np.uint8), use_sheet=False) == ["no_markers", "too_dark"]
    # Markers but no Sheet object: the scale still comes from the marker size.
    m = measure_quality(photos["white_grid"])
    assert m["markers_found"] == 4 and m["px_per_mm"] == pytest.approx(find_sheet(photos["white_grid"]).px_per_mm, abs=0.3)


def test_problems_and_metrics_are_json_ready(photos):
    p = DEGRADATIONS["too_dark"](photos["checkerboard"])
    sheet = find_sheet(p)
    m = measure_quality(p, sheet)
    probs = check_quality(p, sheet, metrics=m)
    assert isinstance(probs[0], Problem) and probs[0].message
    json.dumps({"problems": [q.as_dict() for q in probs], "metrics": m}, allow_nan=False)


def test_grid_run_records_problems_and_warns(tmp_path, capsys, photos):
    good, blurred = tmp_path / "good.png", tmp_path / "blur.png"
    cv2.imwrite(str(good), photos["white_grid"])
    cv2.imwrite(str(blurred), cv2.GaussianBlur(photos["white_grid"], (0, 0), 2.0))
    run_grid(good, tmp_path / "a", "S", 1)
    assert json.load(open(tmp_path / "a" / "run.json"))["quality"]["problems"] == []
    rows = run_grid(blurred, tmp_path / "b", "S", 1)  # warns, still measures
    assert rows and "blurry" in capsys.readouterr().err
    q = json.load(open(tmp_path / "b" / "run.json"))["quality"]
    assert [p["code"] for p in q["problems"]] == ["blurry"] and q["metrics"]["edge_width_mm"] > 0.3


def test_grid_run_without_markers_explains_why(tmp_path, photos):
    path = tmp_path / "nomarkers.png"
    cv2.imwrite(str(path), (cover_markers(photos["white_grid"], {0, 1, 2, 3}) * 0.4).astype(np.uint8))
    with pytest.raises(ValueError, match="(?s)markers.*too dark"):
        run_grid(path, tmp_path / "out", "S", 1)
