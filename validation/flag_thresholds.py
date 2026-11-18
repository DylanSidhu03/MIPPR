"""Flag thresholds from labelled particles: how many wrong results each flag catches and misses.

The app's tunable flags send particles to a reviewer first. Their thresholds are provisional until the
labelled particles photographed on the sheets show which values go with wrong results (docs/PIPELINE.md,
part 7). This takes sheet_check.py's particles.csv (the app's answer next to the known one, box by box)
and, for each flag, tries every threshold the data allows:

| Flag | Score | Flags when | A result counts as wrong when |
|---|---|---|---|
| `flag_size_uncertain` | `size_uncertainty` | above | the length is more than the tolerance off |
| `flag_low_contrast` | `contrast` | below | the length is more than the tolerance off |
| `flag_merged` | `solidity` | below | the length is more than the tolerance off |
| `flag_low_confidence` (colour) | `color_confidence` | below | the colour label is wrong |
| `flag_low_confidence` (shape) | `morphology_confidence` | below | the morphology label is wrong |

For each it reports, per threshold, how many particles get flagged, the wrong results caught and missed,
and the right ones flagged for nothing; and it suggests two thresholds: the lowest share flagged that still
catches `--recall` of the wrong results (default 80%: reviewers see most mistakes), and the best balance of
caught and false alarms (F1). With fewer than MIN_WRONG wrong results the suggestion is withheld.

    python validation/flag_thresholds.py OUT_DIR/particles.csv [--tolerance 0.10] [--recall 0.8] --out thresholds.md

sheet_check.py runs this too and writes OUT_DIR/thresholds.md and thresholds.json.
"""
import argparse
import csv
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "pipeline"))

from mippr.export import LOW_CONTRAST, MERGED_SOLIDITY, SIZE_UNCERTAIN  # noqa: E402

MIN_WRONG = 10  # fewer wrong results than this: show the table, but suggest nothing

# name, flag column, score column, direction ("above"/"below"), what "wrong" means, current threshold
FLAGS = [
    ("size_uncertainty", "flag_size_uncertain", "size_uncertainty", "above", "size", SIZE_UNCERTAIN),
    ("contrast", "flag_low_contrast", "contrast", "below", "size", LOW_CONTRAST),
    ("solidity", "flag_merged", "solidity", "below", "size", MERGED_SOLIDITY),
    ("colour confidence", "flag_low_confidence", "color_confidence", "below", "color", None),
    ("shape confidence", "flag_low_confidence", "morphology_confidence", "below", "morphology", None),
]
WRONG_TEXT = {"size": "length is more than {tol:.0f}% off", "color": "colour label wrong", "morphology": "shape label wrong"}


def _f(v):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def _b(v):
    if v in (True, False, None):
        return v
    return {"true": True, "false": False}.get(str(v).strip().lower())


def is_wrong(rec, kind, tolerance):
    """True/False, or None when the record has no known answer for this kind."""
    if kind == "size":
        e = _f(rec.get("length_error"))
        return None if e is None else abs(e) > tolerance
    ok = _b(rec.get(f"{kind}_correct"))
    return None if ok is None else not ok


def sweep(scores, wrong, direction):
    """[(threshold, flagged, caught, missed, false_alarms)] for every cut between distinct scores."""
    vals = sorted(set(scores))
    if direction == "above":  # flag when score > t
        cuts = [vals[0] - 1e-9] + [(a + b) / 2 for a, b in zip(vals, vals[1:])] + [vals[-1]]
        flagged_at = lambda t: [s > t for s in scores]  # noqa: E731
    else:  # flag when score < t
        cuts = [vals[0]] + [(a + b) / 2 for a, b in zip(vals, vals[1:])] + [vals[-1] + 1e-9]
        flagged_at = lambda t: [s < t for s in scores]  # noqa: E731
    out = []
    for t in cuts:
        fl = flagged_at(t)
        caught = sum(f and w for f, w in zip(fl, wrong))
        out.append((t, sum(fl), caught, sum(wrong) - caught, sum(f and not w for f, w in zip(fl, wrong))))
    return out


def suggest(rows, n_wrong, recall):
    """(threshold for the recall target with the fewest flagged, F1-best threshold); None where not possible.
    A threshold that flags every particle is no use, so it is never suggested."""
    if n_wrong < MIN_WRONG:
        return None, None
    total = max(r[1] for r in rows)
    rows = [r for r in rows if r[1] < total]
    if not rows:
        return None, None
    ok = [r for r in rows if r[2] >= recall * n_wrong]
    by_recall = min(ok, key=lambda r: (r[1], r[4]))[0] if ok else None
    f1 = lambda r: 2 * r[2] / (2 * r[2] + r[3] + r[4]) if r[2] else 0.0  # noqa: E731
    best = max(rows, key=f1)
    return by_recall, (best[0] if f1(best) > 0 else None)


def analyse(recs, tolerance=0.10, recall=0.8):
    """One dict per flag: the sweep, counts and suggestions."""
    out = []
    for name, flag, score, direction, kind, current in FLAGS:
        pairs = [(_f(r.get(score)), is_wrong(r, kind, tolerance)) for r in recs]
        pairs = [(s, w) for s, w in pairs if s is not None and w is not None]
        res = {"name": name, "flag": flag, "score": score, "direction": direction, "wrong_means": kind,
               "current": current, "particles": len(pairs), "wrong": sum(w for _, w in pairs), "rows": [],
               "suggest_recall": None, "suggest_f1": None}
        if pairs:
            scores, wrong = [s for s, _ in pairs], [w for _, w in pairs]
            res["rows"] = sweep(scores, wrong, direction)
            res["suggest_recall"], res["suggest_f1"] = suggest(res["rows"], res["wrong"], recall)
            if current is not None:
                fl = [(s > current) if direction == "above" else (s < current) for s in scores]
                caught = sum(f and w for f, w in zip(fl, wrong))
                res["at_current"] = (sum(fl), caught, res["wrong"] - caught, sum(f and not w for f, w in zip(fl, wrong)))
        out.append(res)
    return out


def _thin(rows, k=12):
    """At most k rows of a sweep, evenly spread, always keeping the ends."""
    if len(rows) <= k:
        return rows
    step = (len(rows) - 1) / (k - 1)
    return [rows[round(i * step)] for i in range(k)]


def markdown(results, tolerance=0.10, recall=0.8):
    L = ["# Flag thresholds from the labelled particles", "",
         f"A result counts as wrong when its {WRONG_TEXT['size'].format(tol=100 * tolerance)}, or its colour or shape "
         f"label differs from the known one. Suggestions: the fewest particles flagged while still catching "
         f"{100 * recall:.0f}% of the wrong results, and the best balance of caught and false alarms. "
         f"With fewer than {MIN_WRONG} wrong results no threshold is suggested. Change a threshold only by a new, "
         "versioned release (docs/PIPELINE.md, part 10).", ""]
    for r in results:
        cmp = "above" if r["direction"] == "above" else "below"
        L += [f"## `{r['flag']}`: {r['name']} (`{r['score']}`, flags {cmp} the threshold)", ""]
        if not r["particles"]:
            L += ["No particles with both this score and a known answer yet.", ""]
            continue
        L.append(f"{r['particles']} particles, {r['wrong']} wrong (the {WRONG_TEXT[r['wrong_means']].format(tol=100 * tolerance)}).")
        if r.get("at_current"):
            fl, c, m, fa = r["at_current"]
            L.append(f"At the current threshold ({r['current']:g}): {fl} flagged, catching {c} of {r['wrong']} wrong, "
                     f"missing {m}, {fa} flagged but right.")
        if r["wrong"] < MIN_WRONG:
            L.append(f"Too few wrong results to suggest a threshold (need {MIN_WRONG}).")
        else:
            sf = "no threshold separates them" if r["suggest_f1"] is None else f"**{r['suggest_f1']:.4g}**"
            if r["suggest_recall"] is None:
                L.append(f"No threshold catches {100 * recall:.0f}% of the wrong results without flagging every particle. "
                         f"Best balance of caught and false alarms: {sf}.")
            else:
                L.append(f"Suggested: **{r['suggest_recall']:.4g}** to catch {100 * recall:.0f}% of the wrong results; "
                         f"{sf} for the best balance.")
        L += ["", f"| Flag {cmp} | Flagged | Wrong caught | Wrong missed | Flagged but right |", "|---|---|---|---|---|"]
        L += [f"| {0 if abs(t) < 1e-6 else t:.4g} | {fl} | {c} | {m} | {fa} |" for t, fl, c, m, fa in _thin(r["rows"])]
        L.append("")
    return "\n".join(L) + "\n"


def summary_json(results):
    return {r["flag"] + ("" if r["flag"] != "flag_low_confidence" else f" ({r['score']})"): {
        "score": r["score"], "direction": r["direction"], "current": r["current"], "particles": r["particles"],
        "wrong": r["wrong"], "suggest_recall": r["suggest_recall"], "suggest_f1": r["suggest_f1"]} for r in results}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("particles", help="particles.csv written by sheet_check.py")
    ap.add_argument("--tolerance", type=float, default=0.10, help="a length more than this far off counts as wrong")
    ap.add_argument("--recall", type=float, default=0.8, help="share of wrong results the suggested threshold catches")
    ap.add_argument("--out", help="write the report here (default: print it)")
    a = ap.parse_args(argv)
    with open(a.particles, newline="", encoding="utf-8-sig") as f:
        recs = list(csv.DictReader(f))
    results = analyse(recs, a.tolerance, a.recall)
    text = markdown(results, a.tolerance, a.recall)
    if a.out:
        Path(a.out).write_text(text)
        Path(a.out).with_suffix(".json").write_text(json.dumps(summary_json(results), indent=2))
        print(f"-> {a.out}")
    else:
        print(text)


if __name__ == "__main__":
    main()
