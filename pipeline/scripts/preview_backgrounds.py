"""Side-by-side previews of background design options, with example particles drawn at true size.

    python scripts/preview_backgrounds.py OUT_DIR

Writes one PNG per background (three options side by side) and a close-up of
the top-left boxes for each option.
"""
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mippr.capture.sheet import Layout, render  # noqa: E402

DPI = 200
OPTIONS = [
    ("1  Compact", dict(box_mm=10.0, line_mm=0.3, box_labels=False)),
    ("2  Standard", dict(box_mm=12.0, line_mm=0.5, box_labels=True)),
    ("3  Large", dict(box_mm=15.0, line_mm=0.8, box_labels=True)),
]
# (box, kind, size mm, BGR) - in scope particles are 0.5-5 mm, fibers can be longer
EXAMPLES = [("A1", "disc", 0.5, (40, 40, 200)), ("A2", "disc", 2.0, (200, 120, 40)), ("A3", "disc", 5.0, (60, 160, 60)),
            ("B2", "fiber", 10.0, (30, 140, 230)), ("B1", "disc", 3.0, (225, 225, 225)), ("C3", "disc", 3.0, (35, 35, 35))]


def draw(img, lay, box, kind, size, color):
    ppm = DPI / 25.4
    r, c = ord(box[0]) - 65, int(box[1:]) - 1
    gx, gy = lay.grid_origin_mm
    cx, cy = (gx + (c + 0.5) * lay.box_mm) * ppm, (gy + (r + 0.5) * lay.box_mm) * ppm
    if kind == "disc":
        cv2.circle(img, (int(cx), int(cy)), max(1, int(size / 2 * ppm)), color, -1, cv2.LINE_AA)
    else:
        pts = cv2.boxPoints(((cx, cy), (size * ppm, 0.3 * ppm), 30))
        cv2.fillPoly(img, [np.round(pts).astype(np.int32)], color, cv2.LINE_AA)


def caption(img, lines, height=150):
    bar = np.full((height, img.shape[1], 3), 255, np.uint8)
    for i, (t, sz, th) in enumerate(lines):
        cv2.putText(bar, t, (20, 45 + i * 42), cv2.FONT_HERSHEY_SIMPLEX, sz, (30, 30, 30), th, cv2.LINE_AA)
    return np.vstack([bar, img])


def main(out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    for bg in ("white_grid", "black_grid", "checkerboard"):
        panels, zooms = [], []
        for name, kw in OPTIONS:
            lay = Layout(bg, "letter", **kw)
            img = cv2.cvtColor(render(lay, DPI), cv2.COLOR_GRAY2BGR)
            for ex in EXAMPLES:
                draw(img, lay, *ex)
            line = "no lines" if bg == "checkerboard" else f"{lay.line_mm:g} mm lines"
            lab = "box labels in margin + in each box" if lay.box_labels else "box labels in margin only"
            info = [(name, 1.1, 3), (f"{lay.box_mm:g} mm boxes, {line}", 0.8, 2),
                    (f"{lay.rows} x {lay.cols} = {lay.rows * lay.cols} boxes per Letter sheet; {lab}", 0.62, 1)]
            panels.append(caption(img, info))
            ppm = DPI / 25.4
            gx, gy = lay.grid_origin_mm
            x0, y0 = int((gx - 7) * ppm), int((gy - 7) * ppm)
            z = img[y0:y0 + int(55 * ppm), x0:x0 + int(55 * ppm)]
            z = cv2.resize(z, (700, 700), interpolation=cv2.INTER_AREA)
            zooms.append(caption(z, [(name + " (close-up, true-scale particles)", 0.75, 2),
                                     ("0.5, 2, 5 mm discs; 10 mm fiber; white and dark 3 mm", 0.6, 1)], 100))
        gap = np.full((panels[0].shape[0], 40, 3), 200, np.uint8)
        sheet = np.hstack([panels[0], gap, panels[1], gap, panels[2]])
        cv2.imwrite(str(out / f"options_{bg}.png"), cv2.resize(sheet, None, fx=0.55, fy=0.55, interpolation=cv2.INTER_AREA))
        zgap = np.full((zooms[0].shape[0], 30, 3), 200, np.uint8)
        cv2.imwrite(str(out / f"closeups_{bg}.png"), np.hstack([zooms[0], zgap, zooms[1], zgap, zooms[2]]))


if __name__ == "__main__":
    main(sys.argv[1])
