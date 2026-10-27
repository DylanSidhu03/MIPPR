"""Compare MIPPR measurements with the lab's ImageJ results for the fragment_area sample.

ImageJ measured cropped_particle.jpg, a straight crop of particle.jpg, at
74.904 um/px. This maps each ImageJ centroid back into the photo, then onto
the rectified board, and pairs it with the nearest MIPPR particle.

    python scripts/compare_imagej.py FRAGMENT_AREA_DIR MIPPR_CSV [--square-mm 10]
"""
import argparse
import sys
from pathlib import Path

import cv2
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mippr.board import find_board  # noqa: E402

IMAGEJ_UM_PER_PX = 74.904


def crop_offset(template):
    """Repeat checkboard.py's crop: bounding box of the largest 4-sided dark contour."""
    gray = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, 100, 255, cv2.THRESH_BINARY_INV)
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    best, best_area = None, 0
    for c in contours:
        approx = cv2.approxPolyDP(c, 0.02 * cv2.arcLength(c, True), True)
        if len(approx) == 4 and cv2.contourArea(c) > best_area:
            best, best_area = approx, cv2.contourArea(c)
    x, y, _, _ = cv2.boundingRect(best)
    return x, y


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("fragment_area")
    ap.add_argument("mippr_csv")
    ap.add_argument("--square-mm", type=float, default=10.0)
    ap.add_argument("--px-per-square", type=int, default=140)
    a = ap.parse_args()
    root = Path(a.fragment_area)
    ij = pd.read_csv(root / "results" / "area_results.csv")
    mp = pd.read_csv(a.mippr_csv)
    ox, oy = crop_offset(cv2.imread(str(root / "template.jpg")))
    board = find_board(cv2.imread(str(root / "particle.jpg")), a.px_per_square)
    pts = np.stack([ij.X / IMAGEJ_UM_PER_PX + ox, ij.Y / IMAGEJ_UM_PER_PX + oy], axis=1)
    rect = cv2.perspectiveTransform(pts.reshape(-1, 1, 2).astype(np.float32), board.homography).reshape(-1, 2)
    um = a.square_mm * 1000 / a.px_per_square
    mp_xy = mp[["x_um", "y_um"]].to_numpy() / um

    pairs = []
    for k, (x, y) in enumerate(rect):
        d = np.hypot(mp_xy[:, 0] - x, mp_xy[:, 1] - y)
        j = int(np.argmin(d))
        pairs.append((k, j, d[j]))
    rows = []
    for k, j, dist in pairs:
        r, m = ij.iloc[k], mp.iloc[j]
        rows.append({
            "imagej": int(r.iloc[0]), "mippr": int(m.particle), "well": m.well, "dist_px": round(dist, 1),
            "ij_area_mm2": r.Area / 1e6, "mp_area_mm2": m.area_um2 / 1e6,
            "ij_feret_mm": r.Feret / 1e3, "mp_feret_mm": m.feret_max_um / 1e3,
            "ij_minferet_mm": r.MinFeret / 1e3, "mp_minferet_mm": m.feret_min_um / 1e3,
            "ij_circ": r["Circ."], "mp_circ": m.circularity,
            "ij_solidity": r.Solidity, "mp_solidity": m.solidity,
        })
    t = pd.DataFrame(rows)
    pd.set_option("display.width", 250)
    print(t.round(3).to_string(index=False))
    good = t[(t.dist_px < 15) & (t.ij_area_mm2 > 0.1)]
    dup = good[good.duplicated("mippr", keep=False)]
    if len(dup):
        print("\nImageJ objects sharing one MIPPR particle (ImageJ split it):", dup.imagej.tolist())
    good = good.drop_duplicates("mippr", keep=False)
    unmatched_ij = t[(t.dist_px >= 15) | (t.ij_area_mm2 <= 0.1)].imagej.tolist()
    unmatched_mp = sorted(set(mp.particle) - set(t[t.dist_px < 15].mippr))
    print(f"\nmatched one-to-one: {len(good)}   ImageJ-only (specks or misses): {unmatched_ij}"
          f"   MIPPR-only: {unmatched_mp}")
    for name in ("area_mm2", "feret_mm", "minferet_mm", "circ", "solidity"):
        rel = good[f"mp_{name}"] / good[f"ij_{name}"] - 1
        print(f"{name:12s} MIPPR vs ImageJ: median {rel.median():+.1%}, "
              f"middle 80% {rel.quantile(.1):+.1%} to {rel.quantile(.9):+.1%}")


if __name__ == "__main__":
    main()
