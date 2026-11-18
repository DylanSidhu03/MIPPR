"""flag_thresholds.py: which thresholds catch wrong results, on hand-made records and the sheet check's output."""
import csv
import json

import flag_thresholds as ft
from test_sheet_check import run  # noqa: F401  (the sheet check on synthetic photos)


def _recs():
    # 20 sizes: wrong exactly when size_uncertainty > 0.12; contrast low on half of the wrong ones
    recs = []
    for i in range(20):
        su = i / 100
        wrong = su > 0.12
        recs.append({"size_uncertainty": su, "length_error": 0.3 if wrong else 0.01,
                     "contrast": 80 if (wrong and i % 2) else 200, "solidity": 0.9,
                     "color_confidence": 0.3 if i < 4 else 0.9, "color_correct": "False" if i < 3 else "True",
                     "morphology_confidence": "", "morphology_correct": ""})
    return recs


def test_sweep_counts_caught_missed_and_false_alarms():
    rows = ft.sweep([0.0, 0.1, 0.2, 0.3], [False, False, True, True], "above")
    assert rows[0][1:] == (4, 2, 0, 2)  # everything flagged
    assert any(r[1:] == (2, 2, 0, 0) for r in rows)  # the clean cut between 0.1 and 0.2
    assert rows[-1][1:] == (0, 0, 2, 0)


def test_suggestions_find_the_cut():
    res = {r["name"]: r for r in ft.analyse(_recs(), tolerance=0.10, recall=0.8)}
    su = res["size_uncertainty"]
    assert su["particles"] == 20 and su["wrong"] == 7
    assert su["suggest_recall"] is None  # 7 wrong < MIN_WRONG: nothing suggested
    many = _recs() + [dict(r, size_uncertainty=r["size_uncertainty"] + 0.001) for r in _recs()]
    su = {r["name"]: r for r in ft.analyse(many)}["size_uncertainty"]
    assert su["wrong"] == 14 and 0.12 < su["suggest_f1"] < 0.13 and su["at_current"][1] == 14
    assert {r["name"]: r for r in ft.analyse(many)}["shape confidence"]["particles"] == 0  # no shape answers


def test_markdown_and_json():
    res = ft.analyse(_recs())
    text = ft.markdown(res)
    assert "## `flag_size_uncertain`" in text and "Too few wrong results" in text and "No particles" in text
    js = ft.summary_json(res)
    assert set(js) >= {"flag_size_uncertain", "flag_low_contrast", "flag_merged", "flag_low_confidence (color_confidence)"}


def test_sheet_check_writes_the_threshold_report(run):
    _, out = run
    assert "# Flag thresholds" in (out / "thresholds.md").read_text()
    assert "flag_size_uncertain" in json.loads((out / "thresholds.json").read_text())
    rows = list(csv.DictReader(open(out / "particles.csv")))
    assert {"contrast", "solidity", "color_confidence", "morphology_confidence"} <= set(rows[0])
    assert any(r["contrast"] for r in rows)
