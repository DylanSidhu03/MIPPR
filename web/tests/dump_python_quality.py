"""Degraded synthetic photos and the Python quality check, for the JS quality / white-balance parity test.

Run from the repo root: .venv/bin/python web/tests/dump_python_quality.py
Writes web/tests/fixtures/quality_<background>.png (colour) and quality.json (committed).

The photos are made like pipeline/tests/test_quality.py's, without sensor noise so they compress
(noise makes a 2400 px colour PNG about 11 MB). Only the good photos are stored: each case lists the
degradation steps, which the JS test applies itself. The covered-marker rectangles are stored as found.
"""
import json
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipeline"))
from mippr.capture.calibration import check_quality, measure_quality, white_balance  # noqa: E402
from mippr.capture.sheet import BACKGROUNDS, Layout, detect_markers, find_sheet  # noqa: E402
from mippr.capture.synthetic import draw_particle, photograph, sheet_bgr  # noqa: E402

OUT = Path(__file__).resolve().parent / "fixtures"
DPI = 300


def good_photo(background, seed=2, color_patches=False):
    lay = Layout(background, "letter", color_patches=color_patches)
    img = sheet_bgr(lay, DPI)
    draw_particle(img, lay, DPI, "B2", "disc", 2.0, (40, 40, 200))
    draw_particle(img, lay, DPI, "F7", "rect", 9.0, (200, 120, 40), offset_mm=(2, 0), aspect=12, angle=10)
    draw_particle(img, lay, DPI, "K9", "disc", 0.6, (20, 180, 220))
    img = (img.astype(np.float32) * 0.85).astype(np.uint8)
    return photograph(img, seed=seed, k1=-0.03, noise=0.0)


def cover_rects(p, which):
    found = detect_markers(p)
    rects = []
    for i, (mid, c) in enumerate(sorted(found.items())):
        if i in which:
            (x0, y0), (x1, y1) = c.min(0).astype(int) - 10, c.max(0).astype(int) + 10
            rects.append([int(x0), int(y0), int(x1), int(y1)])
    return rects


def apply(p, step):
    kind, arg = step
    if kind == "gauss":
        return cv2.GaussianBlur(p, (0, 0), arg)
    if kind == "motion":
        k = np.zeros((arg, arg), np.float32)
        k[arg // 2, :] = 1.0 / arg
        return cv2.filter2D(p, -1, k)
    if kind == "scale":
        return np.clip(p * arg, 0, 255).astype(np.uint8)
    if kind == "glare":
        h, w = p.shape[:2]
        yy, xx = np.indices((h, w))
        spot = np.clip(1.5 - np.hypot(xx - w / 2, yy - h / 2) / arg, 0, 1)
        return np.clip(p.astype(np.float32) + 255 * spot[..., None], 0, 255).astype(np.uint8)
    if kind == "shadow":
        w = p.shape[1]
        ramp = np.clip((np.arange(w) - 0.45 * w) / (0.1 * w), 0, 1)
        return (p.astype(np.float32) * (1 - (1 - arg) * ramp)[None, :, None]).astype(np.uint8)
    if kind == "tint":
        q = p.astype(np.float32) / 255
        q[..., 0] **= 0.7
        return (q * 255).astype(np.uint8)
    if kind == "cover":
        q = p.copy()
        for x0, y0, x1, y1 in arg:
            q[y0:y1, x0:x1] = (60, 50, 40)  # a finger
        return q
    if kind == "resize":
        return cv2.resize(p, None, fx=arg, fy=arg, interpolation=cv2.INTER_AREA)
    raise ValueError(kind)


DEGRADATIONS = {  # as in pipeline/tests/test_quality.py; "cover" gets its rectangles per photo
    "good": [],
    "blurry": [("gauss", 2.0)],
    "motion": [("motion", 7)],
    "too_dark": [("scale", 0.45)],
    "overexposed": [("scale", 1.4)],
    "glare": [("glare", 25)],
    "uneven_light": [("shadow", 0.45)],
    "color_cast": [("tint", None)],
    "marker_missing": [("cover", {1})],
    "low_resolution": [("resize", 0.8)],
    "two_missing": [("cover", {1, 2})],
}
NO_SHEET = {  # the checks without a Sheet object
    "markers_only": [],
    "no_markers": [("cover", {0, 1, 2, 3})],
    "no_markers_blurry": [("cover", {0, 1, 2, 3}), ("gauss", 3.0)],
    "no_markers_dark": [("cover", {0, 1, 2, 3}), ("scale", 0.4)],
}


def case(name, background, base, steps, use_sheet):
    p = base
    done = []
    for kind, arg in steps:
        if kind == "cover":
            arg = cover_rects(p, arg)
        p = apply(p, (kind, arg))
        done.append([kind, arg])
    sheet = None
    if use_sheet:
        try:
            sheet = find_sheet(p)
        except ValueError:
            pass
    m = measure_quality(p, sheet)
    out = {"name": name, "photo": f"quality_{background}.png", "steps": done, "useSheet": use_sheet,
           "sheetFound": sheet is not None, "metrics": m,
           "problems": [q.as_dict() for q in check_quality(p, sheet, metrics=m)]}
    if sheet is not None:
        gains, report = white_balance(sheet, p)
        out["pxPerMm"] = float(sheet.px_per_mm)
        out["whiteBalance"] = {"gains": gains.tolist(), "report": report}
    return out


cases = []
for bg in BACKGROUNDS:
    base = good_photo(bg)
    cv2.imwrite(str(OUT / f"quality_{bg}.png"), base, [cv2.IMWRITE_PNG_COMPRESSION, 9])
    base = cv2.imread(str(OUT / f"quality_{bg}.png"))
    for name, steps in DEGRADATIONS.items():
        if name == "uneven_light" and bg == "black_grid":
            continue
        cases.append({"background": bg, **case(name, bg, base, steps, True)})
    if bg == "white_grid":
        for name, steps in NO_SHEET.items():
            cases.append({"background": bg, **case(name, bg, base, steps, False)})
# The coloured-patch version of a sheet: found, and its patches reported after white balance.
base = good_photo("checkerboard", color_patches=True)
cv2.imwrite(str(OUT / "quality_checkerboard_color.png"), base, [cv2.IMWRITE_PNG_COMPRESSION, 9])
base = cv2.imread(str(OUT / "quality_checkerboard_color.png"))
c = case("good_color_patches", "checkerboard_color", base, [], True)
c["photo"] = "quality_checkerboard_color.png"
cases.append({"background": "checkerboard", **c})
for c in cases:
    print(c["background"], c["name"], [q["code"] for q in c["problems"]])
(OUT / "quality.json").write_text(json.dumps({"opencv": cv2.__version__, "cases": cases}) + "\n")
print(f"Wrote {len(cases)} cases to {(OUT / 'quality.json').relative_to(ROOT)}")
