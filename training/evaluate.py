"""Part 10: how good a model is on one split: accuracy per class, confusion matrix, macro F1 and
calibration of the confidences (expected calibration error).

    python training/evaluate.py PREDICTIONS.csv [--out report.json]

Works from saved predictions (predictions_<split>.csv, written by train.py or infer.py), so it needs
no torch. A predictions file has one row per particle: particle_ref, sample_id, label (the true
class), pred, confidence, runner_up, runner_up_confidence and p_<class> for every class.

Report only on val while developing. The test split is for the final number of a training run,
and the gold set is for gate.py; never tune settings on either.
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from common import read_csv, write_csv, write_json  # noqa: E402

ECE_BINS = 10


def prediction_rows(refs, labels, probs, classes, extra=None):
    """Rows of a predictions file from class probabilities (N x C, columns in `classes` order)."""
    rows = []
    for i, (ref, lab) in enumerate(zip(refs, labels)):
        p = np.asarray(probs[i], float)
        order = np.argsort(-p, kind="stable")
        r = {"particle_ref": ref, "label": lab, "pred": classes[order[0]], "confidence": f"{p[order[0]]:.6f}",
             "runner_up": classes[order[1]] if len(classes) > 1 else "",
             "runner_up_confidence": f"{p[order[1]]:.6f}" if len(classes) > 1 else ""}
        r.update({f"p_{c}": f"{p[j]:.6f}" for j, c in enumerate(classes)})
        if extra:
            r.update(extra[i])
        rows.append(r)
    return rows


def write_predictions(path, rows, classes):
    cols = ["particle_ref", "sample_id", "label", "pred", "confidence", "runner_up", "runner_up_confidence"]
    write_csv(path, rows, cols + [f"p_{c}" for c in classes])


def read_predictions(path):
    """(rows, classes) of a predictions file."""
    rows = read_csv(path)
    classes = [k[2:] for k in (rows[0] if rows else {}) if k.startswith("p_")]
    return rows, classes


def confusion(labels, preds, classes):
    """C x C counts: row = true class, column = predicted class. Labels outside `classes` are ignored."""
    idx = {c: i for i, c in enumerate(classes)}
    m = np.zeros((len(classes), len(classes)), int)
    for t, p in zip(labels, preds):
        if t in idx and p in idx:
            m[idx[t], idx[p]] += 1
    return m


def expected_calibration_error(confidences, correct, bins=ECE_BINS):
    """(ece, table): the share-weighted gap between confidence and accuracy, in equal-width bins."""
    conf = np.asarray(confidences, float)
    ok = np.asarray(correct, float)
    table, ece = [], 0.0
    edges = np.linspace(0, 1, bins + 1)
    for lo, hi in zip(edges[:-1], edges[1:]):
        sel = (conf > lo) & (conf <= hi) if lo > 0 else (conf >= lo) & (conf <= hi)
        n = int(sel.sum())
        if n:
            acc, mean_conf = float(ok[sel].mean()), float(conf[sel].mean())
            ece += n / len(conf) * abs(acc - mean_conf)
            table.append({"from": round(float(lo), 3), "to": round(float(hi), 3), "n": n,
                          "accuracy": acc, "mean_confidence": mean_conf})
    return float(ece), table


def metrics(labels, preds, confidences, classes):
    """Accuracy, macro F1, per-class recall (accuracy per class), precision and F1, confusion, ECE.

    Macro F1 averages over the classes that occur in `labels` (a class with no true examples has no
    recall to measure, so it would only add noise)."""
    labels, preds = list(labels), list(preds)
    m = confusion(labels, preds, classes)
    per = {}
    f1s = []
    for i, c in enumerate(classes):
        tp, n_true, n_pred = m[i, i], m[i].sum(), m[:, i].sum()
        rec = tp / n_true if n_true else None
        prec = tp / n_pred if n_pred else (None if not n_true else 0.0)
        f1 = (2 * prec * rec / (prec + rec) if prec and rec else 0.0) if n_true else None
        per[c] = {"n": int(n_true), "recall": None if rec is None else float(rec),
                  "precision": None if prec is None else float(prec), "f1": None if f1 is None else float(f1)}
        if f1 is not None:
            f1s.append(f1)
    correct = [t == p for t, p in zip(labels, preds)]
    ece, table = expected_calibration_error(confidences, correct) if labels else (None, [])
    return {"n": len(labels), "accuracy": float(np.mean(correct)) if labels else None,
            "macro_f1": float(np.mean(f1s)) if f1s else None, "per_class": per,
            "confusion": {"classes": classes, "rows_true_cols_pred": m.tolist()},
            "ece": ece, "calibration": table}


def evaluate(predictions, out=None):
    """Report (dict) for a predictions file or rows; written as JSON to `out` if given."""
    if isinstance(predictions, (str, Path)):
        rows, classes = read_predictions(predictions)
    else:
        rows = list(predictions)
        classes = [k[2:] for k in (rows[0] if rows else {}) if k.startswith("p_")]
    rep = metrics([r["label"] for r in rows], [r["pred"] for r in rows],
                  [float(r["confidence"]) for r in rows], classes)
    if out:
        write_json(out, rep)
    return rep


def format_report(rep):
    lines = [f"n = {rep['n']}, accuracy = {_p(rep['accuracy'])}, macro F1 = {_p(rep['macro_f1'])}, "
             f"ECE = {_p(rep['ece'])}", "", "class              n  recall  precision     F1"]
    for c, v in rep["per_class"].items():
        lines.append(f"{c:<16} {v['n']:>3}  {_p(v['recall']):>6}  {_p(v['precision']):>9}  {_p(v['f1']):>5}")
    classes = rep["confusion"]["classes"]
    lines += ["", "confusion (rows true, columns predicted): " + ", ".join(classes)]
    for c, row in zip(classes, rep["confusion"]["rows_true_cols_pred"]):
        lines.append(f"{c:<16} " + " ".join(f"{v:>4}" for v in row))
    return "\n".join(lines)


def _p(v):
    return "-" if v is None else f"{v:.3f}"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("predictions")
    ap.add_argument("--out", help="write the report as JSON")
    a = ap.parse_args(argv)
    rep = evaluate(a.predictions, a.out)
    print(format_report(rep))
    return rep


if __name__ == "__main__":
    main()
