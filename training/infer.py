"""Part 10: predictions for one split of a dataset, from a trained model folder or an exported ONNX file.

    python training/infer.py MODEL DATASET_DIR --split gold --out predictions_gold.csv

MODEL is a MODEL_DIR from train.py (needs torch) or a .onnx file with its .onnx.json sidecar from
export_onnx.py (needs onnxruntime only). gate.py uses this to score models on the gold set.
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from common import read_manifest  # noqa: E402
from evaluate import prediction_rows, write_predictions  # noqa: E402


def softmax(logits):
    z = logits - logits.max(axis=1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(axis=1, keepdims=True)


def onnx_probs(onnx_path, rows, meta, batch_size=64):
    import onnxruntime as ort

    from train import model_inputs
    sess = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
    out = []
    for i in range(0, len(rows), batch_size):
        im, ft = model_inputs(rows[i:i + batch_size], meta)
        out.append(softmax(sess.run(["logits"], {"image": im, "features": ft})[0]))
    return np.concatenate(out) if out else np.zeros((0, len(meta["classes"])))


def load_meta(model):
    p = Path(model)
    return json.loads((Path(str(p) + ".json") if p.suffix == ".onnx" else p / "model.json").read_text())


def predict_split(model, dataset_dir, split, out=None):
    """(rows, meta): prediction rows for every particle in the split. A label the model doesn't know
    is kept (it counts as wrong), so two models are always scored on the same particles."""
    meta = load_meta(model)
    rows, _ = read_manifest(dataset_dir)
    rows = [r for r in rows if r["split"] == split]
    if Path(model).suffix == ".onnx":
        probs = onnx_probs(model, rows, meta)
    else:
        from train import load_model, predict_probs
        net, meta = load_model(model)
        probs = predict_probs(net, rows, meta)
    pr = prediction_rows([r["particle_ref"] for r in rows], [r["label"] for r in rows], probs, meta["classes"],
                         [{"sample_id": r["sample_id"]} for r in rows])
    if out:
        write_predictions(out, pr, meta["classes"])
    return pr, meta


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("model")
    ap.add_argument("dataset")
    ap.add_argument("--split", default="gold")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    pr, meta = predict_split(a.model, a.dataset, a.split, a.out)
    print(f"{len(pr)} predictions ({meta['model_version']}, split {a.split}) -> {a.out}")


if __name__ == "__main__":
    main()
