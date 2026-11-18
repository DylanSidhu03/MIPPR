"""Part 10: export a trained model for ONNX Runtime Web, with its metadata as a JSON sidecar.

    python training/export_onnx.py MODEL_DIR --out web_model/morphology.onnx [--dataset DATASET_DIR]

Writes:
- `morphology.onnx`: inputs `image` (float32 N x 3 x S x S) and `features` (float32 N x F), output
  `logits` (N x C); the batch size is free.
- `morphology.onnx.json`: the sidecar web/src/morphology/model.js reads: classes, crop size, grey,
  image mean / std, feature names with their transform and normalisation, background order,
  model_version, the dataset's manifest hash and metrics (model.json from train.py, plus `onnx`).
- `morphology.expected.json`: a few particles' raw shape values, background, crop file and the
  probabilities torch gave, for a browser parity check.

If onnxruntime is installed the ONNX file is run on the same inputs and the largest difference in
probability from torch is recorded (`onnx.parity_max_abs_diff`); export fails if it is over 1e-4.
"""
import argparse
import json
import sys
import warnings
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from common import FEATURES, read_manifest, write_json  # noqa: E402

OPSET = 17
PARITY_TOLERANCE = 1e-4


def export(model_dir, out_path, dataset_dir=None, n_samples=8):
    """Export; returns the sidecar dict."""
    import torch

    from infer import softmax
    from train import load_model, model_inputs
    net, meta = load_model(model_dir)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    if dataset_dir:
        all_rows, _ = read_manifest(dataset_dir)
        rows = [r for r in all_rows if r["split"] in ("test", "val") and r["label"] in meta["classes"]][:n_samples]
    if rows:
        im, ft = model_inputs(rows, meta)
    else:  # no dataset given: random inputs of the right shape
        g = np.random.default_rng(0)
        s = meta["crop_size"]
        im = g.normal(0, 1, (2, 3, s, s)).astype(np.float32)
        ft = g.normal(0, 1, (2, len(meta["feature_names"]))).astype(np.float32)
    with torch.no_grad():
        ref = torch.softmax(net(torch.from_numpy(im), torch.from_numpy(ft)), 1).numpy()
    kwargs = dict(input_names=["image", "features"], output_names=["logits"], opset_version=OPSET,
                  dynamic_axes={"image": {0: "batch"}, "features": {0: "batch"}, "logits": {0: "batch"}})
    args = (torch.from_numpy(im[:1]), torch.from_numpy(ft[:1]))
    with warnings.catch_warnings():
        # The TorchScript exporter: deprecated from torch 2.9 but still there (2.15), and it needs no
        # extra package. The newer exporter (dynamo=True) needs onnxscript; switch when this one goes.
        warnings.simplefilter("ignore", DeprecationWarning)
        try:
            torch.onnx.export(net, args, str(out_path), dynamo=False, **kwargs)
        except TypeError:  # older torch without the dynamo argument
            torch.onnx.export(net, args, str(out_path), **kwargs)
    onnx_info = {"file": out_path.name, "opset": OPSET, "inputs": ["image", "features"], "outputs": ["logits"],
                 "torch_version": torch.__version__}
    try:
        import onnxruntime as ort
    except ImportError:
        onnx_info["parity_max_abs_diff"] = None
        print("onnxruntime not installed: the ONNX file was not checked against torch")
    else:
        sess = ort.InferenceSession(str(out_path), providers=["CPUExecutionProvider"])
        got = softmax(sess.run(["logits"], {"image": im, "features": ft})[0])
        diff = float(np.abs(got - ref).max())
        onnx_info.update({"parity_max_abs_diff": diff, "onnxruntime_version": ort.__version__,
                          "parity_samples": len(im)})
        if diff > PARITY_TOLERANCE:
            raise RuntimeError(f"ONNX Runtime differs from torch by {diff:.2e} (> {PARITY_TOLERANCE})")
    sidecar = {**meta, "onnx": onnx_info}
    write_json(Path(str(out_path) + ".json"), sidecar)
    expected = {"model_version": meta["model_version"], "classes": meta["classes"], "particles": [
        {"particle_ref": r["particle_ref"], "crop": r["crop"], "background_type": r["background_type"],
         "shape_values": {name: r.get(name, "") for name, _ in FEATURES},
         "features": [float(v) for v in ft[i]], "probabilities": [float(v) for v in ref[i]]}
        for i, r in enumerate(rows)]}
    write_json(out_path.with_name(out_path.stem + ".expected.json"), expected)
    return sidecar


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("model_dir")
    ap.add_argument("--out", required=True, help="path of the .onnx file")
    ap.add_argument("--dataset", help="dataset folder, for real sample inputs in the parity check")
    a = ap.parse_args(argv)
    s = export(a.model_dir, a.out, a.dataset)
    print(f"exported {s['model_version']} -> {a.out} (+ .json sidecar); "
          f"torch vs onnxruntime max diff: {s['onnx']['parity_max_abs_diff']}")
    print(json.dumps({"classes": s["classes"], "features": s["feature_names"]}))


if __name__ == "__main__":
    main()
