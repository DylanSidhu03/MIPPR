"""Printer test kit: check the printer-scale correction on your own photos (docs/PRINTER_TEST.md).

    python -m mippr.cli printer PHOTO [PHOTO ...] [--line-mm 97.0] [--out printer_check/]

For each photo of a printed sheet this reports which paper edges were found, the paper they fit, the
printer's scale from them, and, if you measured the printed 100 mm line with a ruler (--line-mm), how
the two agree. With --out it also saves the photo with the edges it found drawn in, so you can see
whether it found the real edges of the paper.
"""
from pathlib import Path

import cv2
import numpy as np

from .calibration import PRINTER_SCALE_TOL, lens_model, printer_scale
from .sheet import find_sheet

SIDES = ("left", "right", "top", "bottom")


def sheet_to_photo(points_mm, q, H, shape):
    """Photo px of sheet-mm points through the lens model (calibration.lens_model's q and H)."""
    h, w = shape[:2]
    c, n = np.array([w / 2, h / 2]), w / 2
    u = cv2.perspectiveTransform(np.asarray(points_mm, np.float64).reshape(-1, 1, 2), H).reshape(-1, 2)
    p = u.copy()
    for _ in range(8):  # invert u = c + (p - c)(1 + q r^2)
        p = c + (u - c) / (1 + q * (((p - c) / n) ** 2).sum(axis=1, keepdims=True))
    return p


def check(photo_path, line_mm=None, out_dir=None):
    """A dict describing the printer check on one photo (and the diagnostic image's path, with out_dir)."""
    img = cv2.imread(str(photo_path))
    if img is None:
        raise ValueError(f"Could not read {photo_path}.")
    sheet = find_sheet(img)
    ps = printer_scale(sheet, img)
    res = {"photo": Path(photo_path).name, "sheet_paper": sheet.layout.paper, **ps,
           "missing_edges": [s for s in SIDES if ps["edges_mm"][s] is None]}
    if line_mm is not None:
        res["ruler_scale"] = round(line_mm / 100.0, 4)
        if ps["scale"] is not None:
            res["difference_pct"] = round(100 * (ps["scale"] - res["ruler_scale"]), 2)
    s = ps["scale"]
    if s is None:
        res["verdict"] = ("no estimate: " + (f"edge(s) not found: {', '.join(res['missing_edges'])}"
                                           if res["missing_edges"] else "width and height fit no paper size"))
    elif abs(s - 1) <= PRINTER_SCALE_TOL:
        res["verdict"] = f"printed at actual size ({100 * s:.1f}%): nothing to correct"
    else:
        res["verdict"] = f"printer scaled the sheet to {100 * s:.1f}%: the app corrects sizes by this"
    if out_dir is not None:
        q, H, _ = lens_model(sheet, img)
        W, Hh = sheet.layout.size_mm
        vis = img.copy()
        lw = max(2, img.shape[1] // 600)
        for side, v in ps["edges_mm"].items():
            if v is None:
                continue
            t = np.linspace(-10, (Hh if side in ("left", "right") else W) + 10, 60)
            pts = np.stack([np.full_like(t, v), t], 1) if side in ("left", "right") else np.stack([t, np.full_like(t, v)], 1)
            poly = sheet_to_photo(pts, q, H, img.shape).round().astype(np.int32)
            cv2.polylines(vis, [poly], False, (255, 0, 255), lw, cv2.LINE_AA)
        cv2.putText(vis, res["verdict"], (20, 40 + 10 * lw), cv2.FONT_HERSHEY_SIMPLEX, lw / 2, (255, 0, 255), lw, cv2.LINE_AA)
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        res["image"] = str(out / f"{Path(photo_path).stem}_printer_check.jpg")
        cv2.imwrite(res["image"], vis, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return res
