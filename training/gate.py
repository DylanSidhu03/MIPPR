"""Part 10: decide whether a candidate model replaces the current one, on the fixed gold set.

    python training/gate.py --candidate CANDIDATE --current CURRENT --dataset DATASET_DIR --out record.json \\
        [--registry model_versions.json]
    python training/gate.py --candidate-predictions cand_gold.csv --current-predictions cur_gold.csv \\
        --candidate-meta model.json --out record.json

CANDIDATE / CURRENT are a MODEL_DIR (train.py) or a .onnx file with its sidecar (export_onnx.py).
With no current model (the first v3 model), the candidate is accepted if its macro F1 reaches
`--min-macro-f1`.

The candidate is accepted only if, on the same gold particles:
- its macro F1 is not worse than the current model's (less `--f1-tolerance`, default 0), and
- no class's recall (accuracy for that class) drops by more than `--max-class-drop` (default 0.05).
Classes either model doesn't know count: a gold particle of a class the candidate can't predict
is simply wrong.

If the dataset is given, it is also checked that no gold particle is in the train, val or test split.

Writes a version record (JSON) with the fields of the `model_versions` table (database/
migrations: version, kind, trained_on, gold_set_score, approved, created_at) plus the reasons and
both models' gold scores. `--registry` appends it to a JSON list of every version's record.
"""
import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from common import write_json  # noqa: E402
from evaluate import metrics, read_predictions  # noqa: E402

MAX_CLASS_DROP = 0.05
F1_TOLERANCE = 0.0


def gold_set_sha(rows):
    text = "\n".join(f"{r['particle_ref']},{r['label']}" for r in sorted(rows, key=lambda r: r["particle_ref"]))
    return hashlib.sha256(text.encode()).hexdigest()


def _score(rows, classes):
    m = metrics([r["label"] for r in rows], [r["pred"] for r in rows], [float(r["confidence"]) for r in rows], classes)
    return {"n": m["n"], "accuracy": m["accuracy"], "macro_f1": m["macro_f1"], "ece": m["ece"],
            "recall": {c: v["recall"] for c, v in m["per_class"].items() if v["n"]},
            "n_per_class": {c: v["n"] for c, v in m["per_class"].items() if v["n"]},
            "confusion": m["confusion"]}


def decide(candidate_rows, current_rows=None, max_class_drop=MAX_CLASS_DROP, f1_tolerance=F1_TOLERANCE,
           min_macro_f1=0.0, classes=None):
    """(approved, reasons, candidate_score, current_score) from gold-set prediction rows."""
    labels = sorted({r["label"] for r in candidate_rows})
    cls = list(dict.fromkeys((classes or []) + labels + sorted({r["pred"] for r in candidate_rows})
                             + sorted({r["pred"] for r in current_rows or []})))
    cand = _score(candidate_rows, cls)
    if not candidate_rows:
        return False, ["the gold set is empty"], cand, None
    if current_rows is None:
        ok = (cand["macro_f1"] or 0.0) >= min_macro_f1
        why = f"first model: gold macro F1 {cand['macro_f1']:.3f} {'>=' if ok else '<'} minimum {min_macro_f1:.3f}"
        return ok, [why], cand, None
    a = {r["particle_ref"]: r["label"] for r in candidate_rows}
    b = {r["particle_ref"]: r["label"] for r in current_rows}
    if a != b:
        return False, ["the two models were not scored on the same gold particles and labels"], cand, None
    cur = _score(current_rows, cls)
    reasons, ok = [], True
    if (cand["macro_f1"] or 0.0) < (cur["macro_f1"] or 0.0) - f1_tolerance:
        ok = False
        reasons.append(f"macro F1 worse: {cand['macro_f1']:.3f} vs {cur['macro_f1']:.3f}")
    else:
        reasons.append(f"macro F1 {cand['macro_f1']:.3f} vs {cur['macro_f1']:.3f}: not worse")
    for c, r_cur in cur["recall"].items():
        r_cand = cand["recall"].get(c, 0.0)
        if r_cand < r_cur - max_class_drop:
            ok = False
            reasons.append(f"{c}: recall drops {r_cur:.3f} -> {r_cand:.3f} (more than {max_class_drop:.2f})")
    if ok:
        reasons.append(f"no class drops more than {max_class_drop:.2f}")
    return ok, reasons, cand, cur


def gate(candidate_rows, candidate_meta, current_rows=None, current_meta=None, out=None, registry=None,
         dataset_dir=None, **thresholds):
    """Decide, write the version record to `out` (and append it to `registry`), and return it."""
    problems = []
    if dataset_dir:
        from common import read_manifest
        rows, _ = read_manifest(dataset_dir)
        gold = {r["particle_ref"] for r in rows if r["split"] == "gold"}
        leaked = sorted({r["particle_ref"] for r in rows if r["split"] in ("train", "val", "test")} & gold)
        if leaked:
            problems.append(f"gold particles also in train/val/test: {', '.join(leaked[:5])}")
        if candidate_meta.get("manifest_sha256") and dataset_dir:
            from common import sha256_file
            if sha256_file(Path(dataset_dir) / "manifest.csv") != candidate_meta["manifest_sha256"]:
                problems.append("the candidate was trained on a different dataset build than the one given "
                                "(its gold split may differ)")
    ok, reasons, cand, cur = decide(candidate_rows, current_rows, classes=candidate_meta.get("classes"), **thresholds)
    if any(p.startswith("gold particles also") for p in problems):
        ok = False
    record = {
        "version": candidate_meta.get("model_version", ""),
        "kind": "morphology",
        "trained_on": candidate_meta.get("manifest_sha256", ""),
        "gold_set_score": {k: cand[k] for k in ("n", "accuracy", "macro_f1", "ece", "recall", "n_per_class")},
        "approved": bool(ok),
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "replaces": (current_meta or {}).get("model_version") if ok else None,
        "current_version": (current_meta or {}).get("model_version"),
        "reasons": reasons + problems,
        "gold_set_sha256": gold_set_sha(candidate_rows),
        "thresholds": {"max_class_drop": thresholds.get("max_class_drop", MAX_CLASS_DROP),
                       "f1_tolerance": thresholds.get("f1_tolerance", F1_TOLERANCE),
                       "min_macro_f1": thresholds.get("min_macro_f1", 0.0)},
        "candidate_gold": cand,
        "current_gold": cur,
        "classes": candidate_meta.get("classes"),
    }
    if out:
        write_json(out, record)
    if registry:
        p = Path(registry)
        reg = json.loads(p.read_text()) if p.exists() else []
        reg.append({k: record[k] for k in ("version", "kind", "trained_on", "gold_set_score", "approved",
                                           "created_at", "replaces", "reasons", "gold_set_sha256")})
        write_json(p, reg)
    return record


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--candidate", help="MODEL_DIR or .onnx")
    ap.add_argument("--current", help="MODEL_DIR or .onnx of the model in use (omit for the first model)")
    ap.add_argument("--dataset", help="dataset folder with the gold split")
    ap.add_argument("--candidate-predictions")
    ap.add_argument("--current-predictions")
    ap.add_argument("--candidate-meta", help="model.json / .onnx.json, with --candidate-predictions")
    ap.add_argument("--current-meta")
    ap.add_argument("--max-class-drop", type=float, default=MAX_CLASS_DROP)
    ap.add_argument("--f1-tolerance", type=float, default=F1_TOLERANCE)
    ap.add_argument("--min-macro-f1", type=float, default=0.0)
    ap.add_argument("--out", required=True)
    ap.add_argument("--registry")
    a = ap.parse_args(argv)
    if a.candidate:
        from infer import predict_split
        cand_rows, cand_meta = predict_split(a.candidate, a.dataset, "gold")
        cur_rows, cur_meta = predict_split(a.current, a.dataset, "gold") if a.current else (None, None)
    else:
        cand_rows, _ = read_predictions(a.candidate_predictions)
        cand_meta = json.loads(Path(a.candidate_meta).read_text()) if a.candidate_meta else {}
        cur_rows = read_predictions(a.current_predictions)[0] if a.current_predictions else None
        cur_meta = json.loads(Path(a.current_meta).read_text()) if a.current_meta else None
    rec = gate(cand_rows, cand_meta, cur_rows, cur_meta, a.out, a.registry, a.dataset,
               max_class_drop=a.max_class_drop, f1_tolerance=a.f1_tolerance, min_macro_f1=a.min_macro_f1)
    print(("ACCEPT " if rec["approved"] else "REJECT ") + (rec["version"] or "candidate"))
    for r in rec["reasons"]:
        print(f"  {r}")
    return rec


if __name__ == "__main__":
    main()
