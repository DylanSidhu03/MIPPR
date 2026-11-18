"""Dump the Python colour rules, morphology rules and export (parts 4, 5 and export.py) for the JS parity test.

Run from the repo root: .venv/bin/python web/tests/dump_python_export.py
Writes web/tests/fixtures/export_rules.json (colour and morphology rules) and export_rows.json
(measurements from the synthetic grid sample plus hand-made edge cases, with build_rows,
build_summary and the exact CSV text). Non-finite floats are written as {"float": "nan" | "inf" | "-inf"},
since JSON has no NaN.
"""
import csv
import io
import json
import math
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipeline"))
from mippr.capture.calibration import white_balance  # noqa: E402
from mippr.capture.sheet import Layout, find_sheet  # noqa: E402
from mippr.capture.synthetic import draw_particle, photograph, sheet_bgr  # noqa: E402
from mippr.color.rules import (CHROMA_MIN, COLOR_CLASSES, COLOR_RULES_VERSION, PIXEL_CLASSES, SHADES,  # noqa: E402
                               color_classes, label_from_lab, pixel_classes)
from mippr.export import COLUMNS, FLAGS, NOTE, SUMMARY_COLUMNS, build_rows, build_summary  # noqa: E402
from mippr.measurement.geometry import measure  # noqa: E402
from mippr.morphology.rules import MORPHOLOGY_CLASSES, morphology_rules  # noqa: E402
from mippr.segmentation.grid import GridSegmentParams, background_image, box_of, line_band, segment_grid  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures"
DPI = 300
NAN, INF = float("nan"), float("inf")


def plain(v):
    """numpy scalars to Python ones, and non-finite floats to {"float": ...}."""
    if isinstance(v, dict):
        return {k: plain(x) for k, x in v.items()}
    if isinstance(v, (list, tuple, np.ndarray)):
        return [plain(x) for x in v]
    if isinstance(v, (bool, np.bool_)):
        return bool(v)
    if isinstance(v, (int, np.integer)):
        return int(v)
    if isinstance(v, (float, np.floating)):
        v = float(v)
        return v if math.isfinite(v) else {"float": "nan" if math.isnan(v) else ("inf" if v > 0 else "-inf")}
    return v


def write_csv(rows, cols):
    s = io.StringIO(newline="")
    w = csv.DictWriter(s, fieldnames=cols)
    w.writeheader()
    w.writerows(rows)
    return s.getvalue()


# --- Colour --------------------------------------------------------------------------------------

def lab_cie_u8(bgr):
    lab = cv2.cvtColor(np.uint8(bgr).reshape(-1, 1, 3), cv2.COLOR_BGR2LAB).reshape(-1, 3).astype(np.float64)
    return lab * [100 / 255, 1, 1] - [0, 128, 128]


def color_fixture():
    rng = np.random.default_rng(7)
    # Pixels: every hue and lightness band, the chroma and lightness edges, and random 8-bit colours.
    pts = [[L, C * math.cos(math.radians(h)), C * math.sin(math.radians(h))]
           for L in (5, 14, 15, 16, 25, 30, 49.9, 50, 60, 65, 66, 70, 71, 80, 95)
           for C in (0, 11.99, 12, 40) for h in range(0, 360, 15)]
    pts += [[50, 12, 0], [50, 0, 12], [80, 0, 0], [25, 0, 0], [15, 30, 0], [50, -20, -20.0]]
    lab = np.vstack([np.array(pts, float), lab_cie_u8(rng.integers(0, 256, (400, 3)))])
    pixels = {"lab": lab.tolist(), "classes": [str(c) for c in pixel_classes(lab)]}

    def patch(*parts):
        """Lab pixels of solid colours: (BGR, count) parts, plus small noise."""
        bgr = np.vstack([np.tile(np.array(c, float), (n, 1)) for c, n in parts])
        bgr = np.clip(bgr + rng.normal(0, 3, bgr.shape), 0, 255)
        return lab_cie_u8(bgr)

    cases = []
    for bgr in [(40, 40, 200), (200, 80, 30), (60, 160, 60), (245, 245, 245), (20, 20, 20), (128, 128, 128),
                (30, 140, 240), (40, 220, 230), (30, 60, 110), (180, 150, 250), (150, 40, 120)]:
        cases.append((patch((bgr, 60)), None))
    cases += [
        (patch(((200, 80, 30), 50), ((40, 40, 200), 40)), None),  # blue + red: multicolour
        (patch(((200, 80, 30), 80), ((40, 40, 200), 10)), None),  # small second colour
        (patch(((235, 235, 235), 50), ((170, 170, 170), 45)), None),  # white + grey shading
        (patch(((40, 40, 200), 50), ((30, 140, 240), 40)), None),  # red + orange: a shade pair
        (patch(((40, 220, 230), 50), ((60, 160, 60), 40)), None),  # yellow + green: a shade pair
        (patch(((128, 128, 128), 50), ((150, 128, 110), 40)), None),  # grey + a faint blue: close in Lab
        (patch(((20, 20, 20), 50), ((40, 220, 230), 50)), None),  # equal shares
        (patch(((80, 80, 80), 60)), 0.3),  # clear
        (patch(((80, 80, 80), 60)), 0.7),  # opaque grey
        (patch(((200, 80, 30), 60)), 0.2),  # see-through but coloured
        (patch(((200, 80, 30), 50), ((40, 40, 200), 40)), 0.2),  # multicolour is never clear
        (patch(((60, 60, 60), 30)), 0.0),
    ]
    cases.append((np.array([[50.0, 0, 0]]), None))  # one pixel, no second colour
    labels = [{"lab": lab.tolist(), "opacity": op, "result": list(label_from_lab(lab, op))} for lab, op in cases]
    seen = {r["result"][0] for r in labels}
    assert set(COLOR_CLASSES) <= seen | set(pixels["classes"]), set(COLOR_CLASSES) - seen

    # color_classes on small BGR images with a mask (needs OpenCV in both languages).
    images = []
    for k, (fill, second, op) in enumerate([((40, 40, 200), None, None), ((200, 80, 30), (40, 40, 200), None),
                                            ((235, 235, 235), (170, 170, 170), None), ((80, 80, 80), None, 0.3),
                                            ((60, 160, 60), None, None)]):
        img = np.clip(np.full((48, 56, 3), 128.0) + rng.normal(0, 6, (48, 56, 3)), 0, 255).astype(np.uint8)
        m = np.zeros((48, 56), np.uint8)
        cv2.ellipse(m, (28 + k, 24), (17, 12), 15 * k, 0, 360, 1, -1)
        noisy = np.clip(np.array(fill, float) + rng.normal(0, 8, (48, 56, 3)), 0, 255).astype(np.uint8)
        img[m > 0] = noisy[m > 0]
        if second:
            img[24:][m[24:] > 0] = second
        images.append({"shape": list(img.shape), "bgr": img.ravel().tolist(), "mask": m.ravel().tolist(),
                       "opacity": op, "result": list(color_classes(img, m.astype(bool), op))})
    return {"version": COLOR_RULES_VERSION, "classes": COLOR_CLASSES, "pixelClasses": PIXEL_CLASSES,
            "chromaMin": CHROMA_MIN, "shades": sorted(sorted(p) for p in SHADES),
            "pixels": pixels, "labels": labels, "images": images}


# --- Morphology ----------------------------------------------------------------------------------

def morphology_fixture():
    cases = [(8.0, 0.3, 0.9, 1.0, False), (1.05, 0.95, 0.99, 1.0, False), (1.6, 0.7, 0.9, 0.2, False),
             (1.6, 0.7, 0.85, 0.95, False), (1.5, 0.5, 0.9, None, True), (12.0, 0.2, 0.9, 0.2, False),
             (500.0, 0.01, 0.2, 0.9, False), (NAN, NAN, 0.9, None, False), (NAN, 0.9, 0.99, NAN, False),
             (3.0, 0.5, 0.9, 0.5, False), (1.3, 0.85, 0.95, None, False), (1.0, 1.0, 1.0, 0.0, False),
             (INF, 0.0, 0.5, 1.0, False), (2.9, 0.6, 0.8, 0.45, False), (1.2, 0.9, 0.97, 0.4, False),
             (1.0, 0.86, 0.96, 0.6, True), (0.0, 0.0, 0.0, None, False), (1e-300, 1e300, -1.0, 1e-9, False)]
    rng = np.random.default_rng(11)
    for _ in range(60):
        cases.append((float(rng.uniform(0.9, 6)), float(rng.uniform(0.4, 1)), float(rng.uniform(0.7, 1)),
                      None if rng.random() < 0.2 else float(rng.uniform(0, 1)), bool(rng.random() < 0.1)))
    return {"classes": MORPHOLOGY_CLASSES,
            "cases": [{"args": list(c), "result": list(morphology_rules(*c))} for c in cases]}


# --- Export --------------------------------------------------------------------------------------

SCENES = [
    ("black_grid", 3, [("B2", "disc", 2.0, (40, 40, 200), (0, 0), {}),
                       ("D3", "rect", 4.0, (60, 160, 60), (0, 0), {"aspect": 2}),
                       ("F7", "rect", 9.0, (200, 120, 40), (2, 0), {"aspect": 12, "angle": 10}),
                       ("K9", "disc", 0.6, (20, 180, 220), (0, 0), {}),
                       ("H4", "disc", 1.2, (200, 200, 60), (-2.5, 0), {}),
                       ("H4", "disc", 1.2, (200, 200, 60), (2.5, 0), {})]),
    ("white_grid", 2, [("B2", "disc", 2.0, (40, 40, 200), (0, 0), {}),
                       ("C5", "rect", 3.0, (30, 140, 240), (0, 0), {"aspect": 1.4, "angle": 25}),
                       ("E3", "rect", 6.0, (20, 20, 20), (0, 0), {"aspect": 40, "angle": 60}),
                       ("G6", "disc", 0.5, (150, 40, 120), (0, 0), {}),
                       ("J2", "disc", 3.0, (200, 200, 200), (0, 0), {})]),
]


def scene_measurements(background, seed, particles):
    """The measurements cli.run_grid makes for a synthetic photo (the same steps, without writing files)."""
    lay = Layout(background, "letter")
    img = sheet_bgr(lay, DPI)
    for box, shape, size, col, off, kw in particles:
        draw_particle(img, lay, DPI, box, shape, size, col, offset_mm=off, **kw)
    if background == "white_grid":  # a curved fiber in A7, as in test_classify
        ppm = DPI / 25.4
        gx, gy = lay.grid_origin_mm
        cx, cy, r = (gx + 6.5 * lay.box_mm) * ppm, (gy + 0.6 * lay.box_mm) * ppm, 3.5 * ppm
        cv2.ellipse(img, (int(cx), int(cy + r * 0.6)), (int(r), int(r)), 0, -135, -45, (200, 90, 30),
                    int(round(0.35 * ppm)), cv2.LINE_AA)
    photo = photograph(img, seed=seed, k1=-0.03)
    params = GridSegmentParams()
    sheet = find_sheet(photo)
    ppm = sheet.px_per_mm
    rect = sheet.rectify_grid(photo)
    gains, _ = white_balance(sheet, photo)
    balanced = np.clip(rect.astype(np.float32) * gains, 0, 255).astype(np.uint8)
    labels, diff, _ = segment_grid(rect, lay, ppm, params)
    band, _, outer = line_band(lay, ppm, labels.shape, params.line_margin_mm)
    near_line = cv2.dilate(band.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)
    return measure(labels, rect, 1000 / ppm, diff, params.edge_fraction, edge_margin_px=int(np.ceil(outer)) + 2,
                   box_fn=lambda x, y: lay.box_label(*box_of(lay, ppm, x, y)), line_mask=near_line,
                   color_img=balanced, bg_img=background_image(balanced, lay, ppm, params.inset_frac)), 1 / ppm


def edge_cases(base):
    """Hand-made measurements from a real one: the cases the synthetic photos don't reach."""
    def m(particle, **kw):
        d = {k: v for k, v in base.items() if k not in kw.pop("drop", ())}
        d.update(particle=particle, **kw)
        d["_px"] = dict(d["_px"], **kw.get("_px", {}))
        return d

    px = lambda cx, cy: {"cx": np.float64(cx), "cy": np.float64(cy), "x": 5, "y": 7, "w": 30, "h": 12}  # noqa: E731
    return [
        m(1, box="A1", width_unresolved=True, opacity=None, _px=px(10.25, 3.35)),
        m(2, box="A2", drop=("length_um_outer", "length_um_inner", "width_um_outer", "width_um_inner")),
        m(3, box="B4", x_um=5000.0, y_um=900.4, _px=px(0.05, 0.15)),  # three blobs in one box
        m(4, box="B4", x_um=4000.0, y_um=900.6),
        m(5, box="B4", x_um=3000.0, y_um=899.6),
        m(6, box="", x_um=10.0, y_um=10.0), m(7, box=None, x_um=5.0, y_um=10.0),  # no box: numbered 1, 2
        m(8, box="C1", aspect_ratio=NAN, circularity=NAN, solidity=NAN, opacity=None,
          drop=("color_label", "color_confidence", "color_secondary", "color_secondary_fraction")),
        m(9, box="C2", fiber_uniform=True, fiber_length_um=5200.0, fiber_width_um=300.0, feret_max_um=3000.0,
          feret_min_um=600.0, aspect_ratio=5.0),  # bent fiber: sized along the fiber
        m(10, box="C3", fiber_uniform=True, fiber_length_um=3100.0, fiber_width_um=300.0, feret_max_um=3000.0,
          feret_min_um=1000.0, aspect_ratio=3.0),  # straight: Feret decides
        m(11, box="C4", feret_max_um=500.0, feret_min_um=480.0, _contrast=50.0, _touches_edge=True,
          _touches_line=True, length_um_outer=600.0, length_um_inner=400.0),
        m(12, box="C5", feret_max_um=0.0, feret_min_um=0.0, aspect_ratio=NAN, area_um2=1.234e-3,
          perimeter_um=1e22, _contrast=NAN),
        m(13, box="C6", aspect_ratio=500.0, circularity=0.01, solidity=0.2, R_mean=-3.0, G_mean=255.5,
          B_mean=127.5, ced_um=1e-7, convex_area_um2=123456789.0, x_um=0.1 + 0.2, y_um=1 / 3),
        m(14, box="C7", feret_max_um=5000.0, fiber_length_um=4000.0, fiber_uniform=True, fiber_width_um=100.0,
          aspect_ratio=50.0, color_label="clear", color_confidence=0.75, opacity=0.25),
        m(15, box="C8", feret_max_um=4999.999999, feret_min_um=2000.0, aspect_ratio=2.5,
          drop=("_contrast",)),
    ]


def export_fixture():
    sample, mm_per_px = [], []
    for bg, seed, parts in SCENES:
        ms, mpp = scene_measurements(bg, seed, parts)
        sample.append(ms)
        mm_per_px.append(mpp)
    edges = edge_cases(sample[0][0])
    meta = {"date": "2026-11-02", "operator": 'Smith, "J"', "lab": "MIPPR", "setup": "phone\nlamp", "site": None}
    runs = [
        dict(measurements=sample[0], sample_id="S042", picture_label="S042-P03", image_id="photo-1a2b3c4d",
             metadata={"operator": "DS"}, app_version="0.1.0", mm_per_px=mm_per_px[0],
             processed_at="2026-11-02T00:00:00+00:00", background_type="black_grid"),
        dict(measurements=sample[1], sample_id="S042", picture_label="S042-P04", image_id="photo-99887766",
             metadata=meta, app_version="0.1.1", mm_per_px=mm_per_px[1], processed_at="2026-11-03T10:00:00+00:00",
             background_type="white_grid", scale_source="user_corrected", scale_flag=True),
        dict(measurements=edges, sample_id="S043", picture_label="S043-P01", image_id="edge", metadata={},
             app_version="0.1.0", mm_per_px=0.1, processed_at="t", background_type="checkerboard"),
        dict(measurements=edges[:3], sample_id="S044", picture_label="S044-P01", image_id="rejected", metadata={},
             app_version="0.1.0", mm_per_px=0.0714, processed_at="t", background_type="white_grid"),
    ]
    out = []
    all_rows = []
    for run in runs:
        kw = {k: v for k, v in run.items() if k != "measurements"}
        rows = build_rows(run["measurements"], **kw)
        out.append({"args": plain(kw), "measurements": plain(run["measurements"]), "rows": plain(rows),
                    "csv": write_csv(rows, COLUMNS)})
        all_rows += rows
    # Review decisions before the summary: rejected rows are left out, corrected ones counted.
    review = {0: "rejected", 2: "corrected", 3: "confirmed", 7: "corrected", 12: "confirmed"}
    review.update({i: "rejected" for i in range(len(all_rows) - 3, len(all_rows))})  # all of S044
    for i, status in review.items():
        all_rows[i]["review_status"] = status
    all_rows[2]["morphology_label"] = "film"
    summary = build_summary(all_rows)
    return {"note": NOTE, "columns": COLUMNS, "summaryColumns": SUMMARY_COLUMNS, "flags": FLAGS, "runs": out,
            "review": {str(k): v for k, v in review.items()}, "summary": plain(summary),
            "summaryCsv": write_csv(summary, SUMMARY_COLUMNS),
            "floats": [[x, repr(x)] for x in FLOATS],
            "csvOddCells": write_csv([{"a": ""}, {"a": 'say "hi"'}, {"a": "x\ry"}, {"a": None}], ["a"])}


FLOATS = [0.0, -0.0, 1.0, -2.5, 0.1, 0.1 + 0.2, 1 / 3, 2 / 3, 100.0, 123456.789, 1e15, 1e16, 9999999999999998.0,
          1.5e16, 1e22, 1.7976931348623157e308, 5e-324, 2.2250738585072014e-308, 1e-4, 1e-5, 0.00012345, 1.234e-9,
          123e-7, 4.35, 2.0 ** 53, 2.0 ** 53 + 2, 0.5, 1234567890123456.7, 12345678901234567.0, 1e-7, 3.14159e-100,
          6.02214076e23]


if __name__ == "__main__":
    FIXTURES.mkdir(exist_ok=True)
    for name, data in (("export_rules.json", {"color": color_fixture(), "morphology": morphology_fixture()}),
                       ("export_rows.json", export_fixture())):
        p = FIXTURES / name
        p.write_text(json.dumps(plain(data), separators=(",", ":"), allow_nan=False) + "\n")
        print(f"Wrote {p.relative_to(ROOT)} ({p.stat().st_size // 1024} KB)")
