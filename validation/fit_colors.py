"""Check, and fit, the colour rules on the lab's labelled particles.

    python validation/fit_colors.py RESULTS_DIR [--fit]

RESULTS_DIR holds the JSON files from lab_photo_check.py (run_lab_photos.py), which
keep up to 300 CIE Lab pixels for each matched particle. The particle label is decided
from those pixels with the pipeline's own rule (color.rules.label_from_lab); the
pixels are not median-filtered first, unlike in the pipeline, which makes little
difference to the class shares.

Prints the confusion between the lab's colour and the app's. With --fit, it searches
the lightness and chroma limits (WHITE_L, BLACK_L, CHROMA_MIN), scoring each setting
by leave-one-sample-out agreement, so a setting is always judged on samples it was not
fitted on.

These photos are not white-balanced (no grey patch, and their white backgrounds are
clipped), so limits fitted here are a check on the provisional rules, not final values
for the printed sheets.
"""
import argparse
import itertools
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))
from mippr.color import rules  # noqa: E402

LAB_NAMES = {"multicolor (2+ colors)": "multicolor", "multicolor": "multicolor"}


def lab_label(s):
    s = s.strip().lower()
    return LAB_NAMES.get(s, s)


def load(results_dir):
    rows = []
    for f in sorted(Path(results_dir).glob("*.json")):
        d = json.loads(f.read_text())
        for r in d.get("rows", []):
            hand = lab_label(r["hand_color"])
            if hand in ("", "unknown") or not r.get("lab_px"):
                continue
            rows.append({"sample": d["sample"], "background": d["background"], "hand": hand,
                         "lab": np.array(r["lab_px"], float), "opacity": r["color_stats"].get("opacity")})
    return rows


def predict(rows, **params):
    old = {k: getattr(rules, k) for k in params}
    try:
        for k, v in params.items():
            setattr(rules, k, v)
        return [rules.label_from_lab(r["lab"], r["opacity"])[0] for r in rows]
    finally:
        for k, v in old.items():
            setattr(rules, k, v)


def agreement(rows, pred):
    return float(np.mean([p == r["hand"] for p, r in zip(pred, rows)])) if rows else float("nan")


def confusion(rows, pred):
    c = Counter((r["hand"], p) for r, p in zip(rows, pred))
    hands = sorted({r["hand"] for r in rows}, key=lambda h: -sum(v for (a, _), v in c.items() if a == h))
    lines = []
    for h in hands:
        n = sum(v for (a, _), v in c.items() if a == h)
        got = ", ".join(f"{p} {v}" for (a, p), v in c.most_common() if a == h)
        lines.append(f"  {h:11s} {n:4d}  -> {got}")
    return "\n".join(lines)


GRID = {"WHITE_L": [65, 70, 75, 80, 85], "BLACK_L": [20, 25, 30, 35, 40, 45], "CHROMA_MIN": [6, 8, 10, 12, 15, 18]}


def fit(rows):
    """Leave-one-sample-out: for each sample, pick the best setting on the others, score it on that one."""
    settings = [dict(zip(GRID, v)) for v in itertools.product(*GRID.values())]
    by = defaultdict(list)
    for i, r in enumerate(rows):
        by[r["sample"]].append(i)
    hits = np.array([[p == r["hand"] for p, r in zip(predict(rows, **s), rows)] for s in settings])
    held_out, chosen = [], []
    for sample, idx in by.items():
        rest = np.setdiff1d(np.arange(len(rows)), idx)
        if not len(rest):
            continue
        k = int(np.argmax(hits[:, rest].mean(axis=1)))
        chosen.append(tuple(settings[k].values()))
        held_out += list(hits[k, idx])
    best = int(np.argmax(hits.mean(axis=1)))
    return settings[best], float(hits[best].mean()), float(np.mean(held_out)), Counter(chosen)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("results")
    ap.add_argument("--fit", action="store_true")
    a = ap.parse_args()
    rows = load(a.results)
    print(f"{len(rows)} particles with a lab colour, from {len({r['sample'] for r in rows})} samples")
    print("lab colours:", dict(Counter(r["hand"] for r in rows).most_common()))
    pred = predict(rows)
    print(f"\ncurrent rules ({rules.COLOR_RULES_VERSION}): agreement {agreement(rows, pred):.1%}")
    print(confusion(rows, pred))
    for bg in sorted({r["background"] for r in rows}):
        sub = [(r, p) for r, p in zip(rows, pred) if r["background"] == bg]
        print(f"  on {bg} backgrounds: {agreement(*zip(*sub)) if sub else float('nan'):.1%} of {len(sub)}")
    if a.fit:
        best, all_score, cv_score, chosen = fit(rows)
        print(f"\nbest setting on all samples: {best} -> {all_score:.1%}")
        print(f"leave-one-sample-out agreement: {cv_score:.1%} (the honest estimate)")
        print("settings chosen per held-out sample:", dict(chosen.most_common(5)))
        print(confusion(rows, predict(rows, **best)))


if __name__ == "__main__":
    main()
