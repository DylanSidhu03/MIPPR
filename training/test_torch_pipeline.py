"""End to end with torch (skipped without it): synthetic runs -> dataset -> train -> export -> evaluate -> gate."""
import json

import numpy as np
import pytest

torch = pytest.importorskip("torch")

from build_dataset import build  # noqa: E402
from evaluate import evaluate  # noqa: E402
from gate import gate  # noqa: E402
from infer import predict_split  # noqa: E402
from synthetic import make_runs  # noqa: E402
from train import TrainConfig, load_model, make_net, predict_probs, train  # noqa: E402


@pytest.fixture(scope="module")
def dataset(tmp_path_factory):
    d = tmp_path_factory.mktemp("e2e")
    runs, labels, gold = make_runs(d / "syn", n_photos=4, per_class=3)
    build([runs], d / "ds", [labels], gold=gold, fractions=(0.34, 0.33, 0.33))
    return d


def test_train_export_gate(dataset):
    d = dataset
    meta = train(d / "ds", d / "model", TrainConfig(epochs=2, batch_size=8, crop_size=32), log=lambda *a: None)
    assert meta["model_version"].startswith("morphology-") and meta["crop_size"] == 32
    assert set(meta["classes"]) == {"pellet", "fragment", "rubbery_fragment"}
    assert len(meta["feature_names"]) == len(meta["features"]) + 3
    assert (d / "model" / "model.pt").exists() and (d / "model" / "predictions_val.csv").exists()
    net, meta2 = load_model(d / "model")
    assert meta2["model_version"] == meta["model_version"]
    rep = evaluate(d / "model" / "predictions_val.csv")
    assert rep["n"] > 0 and 0 <= rep["accuracy"] <= 1
    # gold predictions from the torch model, then the first-model gate
    rows, _ = predict_split(d / "model", d / "ds", "gold")
    assert len(rows) == 9 and all(abs(sum(float(r[f"p_{c}"]) for c in meta["classes"]) - 1) < 1e-4 for r in rows)
    rec = gate(rows, meta, out=d / "record.json", dataset_dir=d / "ds")
    assert rec["version"] == meta["model_version"] and rec["approved"] and rec["current_version"] is None
    pytest.importorskip("onnx")
    pytest.importorskip("onnxruntime")
    from export_onnx import export
    side = export(d / "model", d / "web" / "morphology.onnx", d / "ds")
    assert side["onnx"]["parity_max_abs_diff"] < 1e-4
    assert json.loads((d / "web" / "morphology.onnx.json").read_text())["classes"] == meta["classes"]
    onnx_rows, _ = predict_split(d / "web" / "morphology.onnx", d / "ds", "gold")
    assert [r["pred"] for r in onnx_rows] == [r["pred"] for r in rows]
    # the ONNX file against the torch folder of the same model: identical, so accepted
    rec = gate(onnx_rows, side, rows, meta)
    assert rec["approved"]


def test_heads_hook_and_probs(dataset):
    with pytest.raises(NotImplementedError):
        make_net(13, 3, head="multitask")
    net = make_net(13, 3)
    out = net(torch.zeros(2, 3, 32, 32), torch.zeros(2, 13))
    assert out.shape == (2, 3)
    net, meta = load_model(dataset / "model")
    p = predict_probs(net, [], meta)
    assert p.shape == (0, len(meta["classes"])) and np.isfinite(p).all()
