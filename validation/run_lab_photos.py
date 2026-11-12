"""Run lab_photo_check.py on a list of the lab's photos and collect one agreement table.

    python validation/run_lab_photos.py PHOTOS.csv PHOTO_DIR SHEET_DIR OUT_DIR

PHOTOS.csv has columns photo,sheet,sample[,extra] (extra: more arguments for
lab_photo_check.py, e.g. "--px-per-mm 30.5"). The photos and sheets are the lab's and
stay in Drive (open question 9); only this list and the summary are committed.
Writes OUT_DIR/<photo>.json and .txt for each photo, and OUT_DIR/summary.md.
"""
import csv
import json
import shlex
import statistics
import subprocess
import sys
from collections import Counter
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent


def run(photos_csv, photo_dir, sheet_dir, out_dir):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for row in csv.DictReader(open(photos_csv)):
        stem = Path(row["photo"]).stem
        js = out_dir / f"{stem}.json"
        cmd = [sys.executable, str(HERE / "lab_photo_check.py"), str(Path(photo_dir) / row["photo"]),
               str(Path(sheet_dir) / row["sheet"]), row["sample"], "--out", str(js)]
        cmd += shlex.split(row.get("extra") or "")
        p = subprocess.run(cmd, capture_output=True, text=True)
        (out_dir / f"{stem}.txt").write_text(p.stdout + p.stderr)
        res = json.loads(js.read_text()) if js.exists() and p.returncode == 0 else {"photo": row["photo"],
                                                                                   "sample": row["sample"]}
        res["log_tail"] = (p.stdout + p.stderr).strip().splitlines()[-1:] if p.returncode else []
        results.append(res)
        print(f"{row['photo']}: {res.get('matched', 0)} matched", flush=True)
    (out_dir / "summary.md").write_text(summary(results))
    return results


def pct(app, hand):
    return 100 * (np.asarray(app) - np.asarray(hand)) / np.asarray(hand)


def summary(results):
    lines = ["| Photo | Sample | Background | Scale (px/mm) | Found / sheet | Matched | r (length) | "
             "Length app vs hand | Width app vs hand | Colour agrees |", "|" + "---|" * 10]
    all_rows = []
    for r in results:
        rows = r.get("rows", [])
        all_rows += rows
        if not rows:
            lines.append(f"| {r['photo']} | {r['sample']} | {r.get('background', '')} | "
                         f"{r.get('px_per_mm', float('nan')):.2f} | {r.get('n_found', '')} / {r.get('n_sheet', '')} | "
                         f"0 | | | | |")
            continue
        L = pct([x["app_length_mm"] for x in rows], [x["hand_length_mm"] for x in rows])
        W = pct([x["app_width_mm"] for x in rows], [x["hand_width_mm"] for x in rows])
        col = sum(x["hand_color"].lower().startswith(x["app_color"][:4]) for x in rows)
        lines.append(f"| {r['photo']} | {r['sample']} | {r['background']} | {r['px_per_mm']:.2f} | "
                     f"{r['n_found']} / {r['n_sheet']} | {r['matched']} | {r['correlation']:.3f} | "
                     f"{statistics.median(L):+.1f}% | {statistics.median(W):+.1f}% | {col}/{len(rows)} |")
    if all_rows:
        lines += ["", f"All matched particles: {len(all_rows)}.", "",
                  "Colour (lab, app), most common:", ""]
        for (h, a), n in Counter((x["hand_color"], x["app_color"]) for x in all_rows).most_common(20):
            lines.append(f"- {h} → {a}: {n}")
        lines += ["", "Shape (lab, app), most common:", ""]
        for (h, a), n in Counter((x["hand_shape"], x["app_morphology"]) for x in all_rows).most_common(10):
            lines.append(f"- {h} → {a}: {n}")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    run(*sys.argv[1:5])
