"""evaluate.py and gate.py on hand-made predictions (no torch)."""
import json

import numpy as np
import pytest

from evaluate import evaluate, expected_calibration_error, metrics, prediction_rows, read_predictions, write_predictions
from gate import decide, gate

CLASSES = ["fragment", "rubbery_fragment", "foam"]


def preds(pairs, conf=0.9):
    """Prediction rows from (true, predicted) pairs."""
    probs = []
    for _, p in pairs:
        v = np.full(len(CLASSES), (1 - conf) / (len(CLASSES) - 1))
        v[CLASSES.index(p)] = conf
        probs.append(v)
    return prediction_rows([f"G-{i}" for i in range(len(pairs))], [t for t, _ in pairs], probs, CLASSES)


def test_metrics():
    m = metrics(["a", "a", "b", "b"], ["a", "b", "b", "b"], [0.9, 0.6, 0.8, 0.7], ["a", "b", "c"])
    assert m["accuracy"] == 0.75
    assert m["per_class"]["a"]["recall"] == 0.5 and m["per_class"]["b"]["precision"] == pytest.approx(2 / 3)
    assert m["macro_f1"] == pytest.approx((2 / 3 + 0.8) / 2)  # c has no true examples: not averaged
    assert m["per_class"]["c"]["recall"] is None
    assert m["confusion"]["rows_true_cols_pred"] == [[1, 1, 0], [0, 2, 0], [0, 0, 0]]


def test_ece():
    ece, table = expected_calibration_error([0.9] * 10, [True] * 9 + [False])
    assert ece == pytest.approx(0.0, abs=1e-12)
    ece, _ = expected_calibration_error([1.0, 1.0], [False, False])
    assert ece == pytest.approx(1.0)
    assert sum(b["n"] for b in table) == 10


def test_prediction_file_round_trip(tmp_path):
    rows = preds([("fragment", "fragment"), ("foam", "fragment"), ("rubbery_fragment", "rubbery_fragment")])
    assert rows[0]["runner_up"] in CLASSES and float(rows[0]["runner_up_confidence"]) == pytest.approx(0.05)
    write_predictions(tmp_path / "p.csv", rows, CLASSES)
    back, classes = read_predictions(tmp_path / "p.csv")
    assert classes == CLASSES and len(back) == 3
    rep = evaluate(tmp_path / "p.csv", tmp_path / "r.json")
    assert rep["accuracy"] == pytest.approx(2 / 3)
    assert json.loads((tmp_path / "r.json").read_text())["n"] == 3


GOLD = [("fragment", "fragment")] * 6 + [("rubbery_fragment", "rubbery_fragment")] * 4 + [("foam", "foam")] * 2


def test_gate_accepts_a_better_model():
    cur = preds(GOLD[:5] + [("fragment", "foam")] + GOLD[6:])
    ok, reasons, cand, prev = decide(preds(GOLD), cur)
    assert ok and cand["macro_f1"] == 1.0 and prev["macro_f1"] < 1.0


def test_gate_rejects_a_class_drop_even_if_macro_f1_is_equal():
    cur = preds(GOLD)
    worse_foam = GOLD[:10] + [("foam", "foam"), ("foam", "fragment")]
    ok, reasons, _, _ = decide(preds(worse_foam), cur)
    assert not ok and any("foam" in r for r in reasons)
    ok, _, _, _ = decide(preds(worse_foam), cur, max_class_drop=0.6, f1_tolerance=0.5)
    assert ok


def test_gate_first_model_and_mismatched_gold(tmp_path):
    ok, reasons, _, prev = decide(preds(GOLD), None, min_macro_f1=0.5)
    assert ok and prev is None and "first model" in reasons[0]
    ok, reasons, _, _ = decide(preds(GOLD), preds(GOLD[:-1]))
    assert not ok and "same gold particles" in reasons[0]
    # a candidate without a class the current model has: those gold particles are wrong
    cur = preds(GOLD)
    no_foam = GOLD[:10] + [("foam", "fragment")] * 2
    ok, reasons, cand, _ = decide(preds(no_foam), cur)
    assert not ok and cand["recall"]["foam"] == 0.0
    rec = gate(preds(GOLD), {"model_version": "morphology-new", "manifest_sha256": "abc", "classes": CLASSES},
               cur, {"model_version": "morphology-old"}, out=tmp_path / "rec.json", registry=tmp_path / "reg.json")
    assert rec["approved"] and rec["replaces"] == "morphology-old" and rec["kind"] == "morphology"
    assert set(rec) >= {"version", "trained_on", "gold_set_score", "approved", "created_at"}
    gate(preds(no_foam), {"model_version": "morphology-bad"}, cur, {"model_version": "morphology-new"},
         registry=tmp_path / "reg.json")
    reg = json.loads((tmp_path / "reg.json").read_text())
    assert [r["approved"] for r in reg] == [True, False]
