"""Printer scale from the paper's edges (calibration.py printer_scale), for the JS parity test.

Run from the repo root: .venv/bin/python web/tests/dump_python_printer.py
Writes web/tests/fixtures/printer.json and two photos of sheets a printer scaled ("fit to page");
the quality_*.png photos (printed at 100%) are reused.
"""
import json
import sys
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipeline"))
from mippr.capture.calibration import lens_model, printer_problem, printer_scale  # noqa: E402
from mippr.capture.sheet import Layout, find_sheet  # noqa: E402
from mippr.capture.synthetic import draw_particle, photograph, printed, sheet_bgr  # noqa: E402

OUT = Path(__file__).resolve().parent / "fixtures"
DPI = 150
SCALED = [("printer_white_grid_97.png", "white_grid", "letter", 0.97, None),
          ("printer_checkerboard_a4_on_letter.png", "checkerboard", "a4", 0.94, "letter")]
for name, bg, paper, scale, on in SCALED:
    lay = Layout(bg, paper)
    img = sheet_bgr(lay, DPI)
    draw_particle(img, lay, DPI, "B2", "disc", 2.0, (40, 40, 200))
    photo = photograph(printed(img, lay, DPI, scale, on), seed=1, out_width=1800, noise=0.0)
    cv2.imwrite(str(OUT / name), photo, [cv2.IMWRITE_PNG_COMPRESSION, 9])

cases = []
for name in [s[0] for s in SCALED] + ["quality_white_grid.png", "quality_black_grid.png", "quality_checkerboard.png"]:
    photo = cv2.imread(str(OUT / name))
    sheet = find_sheet(photo)
    q, _, rms = lens_model(sheet, photo)
    ps = printer_scale(sheet, photo)
    p = printer_problem(ps)
    cases.append({"photo": name, "q": q, "rms": rms, "printerScale": ps, "problem": p.as_dict() if p else None,
                  "problemWithLine": (printer_problem(ps, 98.5).as_dict() if printer_problem(ps, 98.5) else None)})
    print(name, ps["scale"], ps["paper"], p.code if p else None)
(OUT / "printer.json").write_text(json.dumps({"cases": cases}, indent=1) + "\n")
