"""Part 10: train the v3 morphology model (part 5) on crops + shape values + background type.

    python training/train.py DATASET_DIR --out MODEL_DIR [--epochs 30] [--backbone small|mobilenet_v3_small]

One shared model for the three sheets, with the background type as an input (Drive decision):

    crop on grey (CROP_SIZE x CROP_SIZE) -> small CNN ----------------\\
                                                                       concat -> MLP -> class logits
    shape values (normalised) + background one-hot -> small MLP ------/

The CNN is a compact 4-block conv net by default (`small`, fast on a laptop CPU), or torchvision's
MobileNetV3-Small (`mobilenet_v3_small`, needs torchvision; `--pretrained` downloads ImageNet weights).

Training: augmentation as decided (common.augment: rotations, flips, small perspective, limited
scaling, mild brightness / white balance, no hue shifts), class weights against imbalance, labeller
weights (community 0.5), AdamW, early stopping on the validation macro F1. Only the train split is
trained on; val picks the epoch; test is reported; gold is never touched here (gate.py).

Writes MODEL_DIR/model.pt (weights), model.json (the sidecar: classes, inputs, feature names and
normalisation, crop size, grey, model_version, the dataset's manifest hash, metrics, settings),
predictions_val.csv / predictions_test.csv (for evaluate.py) and history.csv.

Comparing a classifier chain with a multi-task model (Drive open question 5) is left as a hook:
`--head` takes only `single` today; see `make_net`.

torch is imported only inside the functions that need it, so the rest of training/ (and the
repo's tests) run without it.
"""
import argparse
import hashlib
import io
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from common import (AUGMENT_DEFAULTS, BACKGROUNDS, CROP_SIZE, FEATURES, GREY, IMAGE_MEAN, IMAGE_STD,  # noqa: E402
                    MORPHOLOGY_CLASSES, augment, feature_names, feature_stats, feature_vector, image_array,
                    prepare_image, read_crop, read_manifest, write_csv, write_json)
from evaluate import metrics, prediction_rows, write_predictions  # noqa: E402

IMAGENET_MEAN, IMAGENET_STD = [0.485, 0.456, 0.406], [0.229, 0.224, 0.225]
SIDECAR_FORMAT = "mippr-morphology-model"
SIDECAR_VERSION = 1


@dataclass
class TrainConfig:
    epochs: int = 30
    batch_size: int = 32
    lr: float = 1e-3
    weight_decay: float = 1e-4
    patience: int = 6               # epochs without a better val macro F1 before stopping
    crop_size: int = CROP_SIZE
    grey: int = GREY
    backbone: str = "small"         # small | mobilenet_v3_small
    pretrained: bool = False        # mobilenet_v3_small only: ImageNet weights (a download)
    head: str = "single"            # single; chain / multitask: the open-question-5 hook
    min_class_count: int = 1        # classes with fewer train examples are left out (recorded)
    class_weights: bool = True
    seed: int = 0
    device: str = "cpu"             # cpu | cuda | auto
    augment: dict = field(default_factory=lambda: dict(AUGMENT_DEFAULTS))
    model_version: str = ""         # default: morphology-<date>-<hash of the weights>


def choose_classes(train_rows, min_count=1):
    """The model's classes: labels with at least `min_count` train examples, in MORPHOLOGY_CLASSES order."""
    n = {}
    for r in train_rows:
        n[r["label"]] = n.get(r["label"], 0) + 1
    known = [c for c in MORPHOLOGY_CLASSES if n.get(c, 0) >= min_count]
    return known + sorted(c for c in n if c not in MORPHOLOGY_CLASSES and n[c] >= min_count)


def class_weight_vector(train_rows, classes):
    """total / (classes x count) per class: rare classes count more in the loss."""
    counts = np.array([sum(r["label"] == c for r in train_rows) for c in classes], float)
    return counts.sum() / (len(classes) * np.maximum(counts, 1))


def model_inputs(rows, meta, rng=None, aug=None):
    """(images N x 3 x S x S, features N x F) float32 for manifest rows; augmented if `rng` is given."""
    imgs, feats = [], []
    for r in rows:
        crop = read_crop(r["crop_path"])
        if rng is not None:
            crop = augment(crop, rng, aug)
        imgs.append(image_array(prepare_image(crop, meta["crop_size"], meta["grey"]), meta["image_mean"],
                                meta["image_std"]))
        feats.append(feature_vector(r, meta["features"], meta["backgrounds"]))
    return np.stack(imgs), np.stack(feats)


def make_net(n_features, n_classes, backbone="small", head="single", pretrained=False):
    """The torch module: forward(image, features) -> logits.

    Hook for open question 5 (classifier chain vs multi-task): `head="chain"` would add the colour
    class probabilities (from the colour rules, out-of-fold) to `features`; `head="multitask"` would
    share the image and feature branches and add one output head per characteristic (colour,
    morphology). Both need colour labels in the manifest first; neither is built yet."""
    import torch
    from torch import nn

    if head != "single":
        raise NotImplementedError(f"head={head!r}: only 'single' is built; chain and multitask are the "
                                  "open-question-5 comparison (see make_net)")

    def block(cin, cout):
        return nn.Sequential(nn.Conv2d(cin, cout, 3, padding=1, bias=False), nn.BatchNorm2d(cout), nn.ReLU(inplace=True),
                             nn.Conv2d(cout, cout, 3, padding=1, bias=False), nn.BatchNorm2d(cout),
                             nn.ReLU(inplace=True), nn.MaxPool2d(2))

    if backbone == "small":
        image_net = nn.Sequential(block(3, 16), block(16, 32), block(32, 64), block(64, 96),
                                  nn.AdaptiveAvgPool2d(1), nn.Flatten())
        image_dim = 96
    elif backbone == "mobilenet_v3_small":
        import torchvision
        weights = torchvision.models.MobileNet_V3_Small_Weights.DEFAULT if pretrained else None
        m = torchvision.models.mobilenet_v3_small(weights=weights)
        image_net = nn.Sequential(m.features, m.avgpool, nn.Flatten())
        image_dim = 576
    else:
        raise ValueError(f"unknown backbone {backbone!r}")

    class MorphologyNet(nn.Module):
        def __init__(self):
            super().__init__()
            self.image_net = image_net
            self.feature_net = nn.Sequential(nn.Linear(n_features, 32), nn.ReLU(), nn.Linear(32, 32), nn.ReLU())
            self.head = nn.Sequential(nn.Dropout(0.2), nn.Linear(image_dim + 32, 64), nn.ReLU(),
                                      nn.Linear(64, n_classes))

        def forward(self, image, features):
            return self.head(torch.cat([self.image_net(image), self.feature_net(features)], dim=1))

    return MorphologyNet()


def _device(name):
    import torch
    if name == "auto":
        return torch.device("cuda" if torch.cuda.is_available() else "cpu")
    return torch.device(name)


def predict_probs(net, rows, meta, batch_size=64, device="cpu"):
    """N x C class probabilities (no augmentation)."""
    import torch
    net.eval()
    out = []
    with torch.no_grad():
        for i in range(0, len(rows), batch_size):
            im, ft = model_inputs(rows[i:i + batch_size], meta)
            logits = net(torch.from_numpy(im).to(device), torch.from_numpy(ft).to(device))
            out.append(torch.softmax(logits, 1).cpu().numpy())
    return np.concatenate(out) if out else np.zeros((0, len(meta["classes"])))


def load_model(model_dir, device="cpu"):
    """(net, meta) from a MODEL_DIR written by train()."""
    import json

    import torch
    d = Path(model_dir)
    meta = json.loads((d / "model.json").read_text())
    net = make_net(len(feature_names(meta["features"], meta["backgrounds"])), len(meta["classes"]),
                   meta["backbone"], meta["head"])
    net.load_state_dict(torch.load(d / "model.pt", map_location=device, weights_only=True))
    return net.to(device).eval(), meta


def train(dataset_dir, out_dir, config=None, log=print):
    """Train on DATASET_DIR's train split; returns the sidecar dict (also written to model.json)."""
    import torch
    import torch.nn.functional as F

    cfg = config or TrainConfig()
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    rows, info = read_manifest(dataset_dir)
    split = {s: [r for r in rows if r["split"] == s] for s in ("train", "val", "test")}
    classes = choose_classes(split["train"], cfg.min_class_count)
    if len(classes) < 2:
        raise ValueError(f"need at least two classes with {cfg.min_class_count}+ training examples; have {classes}")
    dropped = {s: sum(r["label"] not in classes for r in v) for s, v in split.items()}
    split = {s: [r for r in v if r["label"] in classes] for s, v in split.items()}
    rng = np.random.default_rng(cfg.seed)
    torch.manual_seed(cfg.seed)
    device = _device(cfg.device)
    pretrained_stats = cfg.backbone == "mobilenet_v3_small" and cfg.pretrained
    meta = {
        "format": SIDECAR_FORMAT, "format_version": SIDECAR_VERSION, "model_version": "",
        "classes": classes, "crop_size": cfg.crop_size, "grey": cfg.grey, "channel_order": "RGB",
        "image_mean": IMAGENET_MEAN if pretrained_stats else IMAGE_MEAN,
        "image_std": IMAGENET_STD if pretrained_stats else IMAGE_STD,
        "features": feature_stats(split["train"], FEATURES), "backgrounds": BACKGROUNDS,
        "inputs": {"image": "float32 [N, 3, crop_size, crop_size], RGB, (x / 255 - image_mean) / image_std",
                   "features": "float32 [N, len(features) + len(backgrounds)]: (transform(x) - mean) / std, "
                               "missing -> 0; then the background type one-hot"},
        "outputs": {"logits": "float32 [N, len(classes)]; softmax gives the class probabilities"},
        "backbone": cfg.backbone, "head": cfg.head,
        "manifest_sha256": info["manifest_sha256"], "dataset_built_at": info.get("built_at"),
    }
    meta["feature_names"] = feature_names(meta["features"], meta["backgrounds"])
    net = make_net(len(meta["feature_names"]), len(classes), cfg.backbone, cfg.head, cfg.pretrained).to(device)
    opt = torch.optim.AdamW(net.parameters(), lr=cfg.lr, weight_decay=cfg.weight_decay)
    cw = torch.tensor(class_weight_vector(split["train"], classes) if cfg.class_weights else np.ones(len(classes)),
                      dtype=torch.float32, device=device)
    y_all = np.array([classes.index(r["label"]) for r in split["train"]])
    w_all = np.array([float(r.get("weight") or 1.0) for r in split["train"]], np.float32)
    best, best_key, since, history = None, None, 0, []
    log(f"train {len(split['train'])}, val {len(split['val'])}, test {len(split['test'])}; classes {classes}")
    for epoch in range(1, cfg.epochs + 1):
        net.train()
        order = rng.permutation(len(split["train"]))
        total, wsum = 0.0, 0.0
        for i in range(0, len(order), cfg.batch_size):
            idx = order[i:i + cfg.batch_size]
            if len(idx) < 2:  # BatchNorm needs two or more
                continue
            im, ft = model_inputs([split["train"][j] for j in idx], meta, rng, cfg.augment)
            y = torch.from_numpy(y_all[idx]).to(device)
            sw = torch.from_numpy(w_all[idx]).to(device)
            logits = net(torch.from_numpy(im).to(device), torch.from_numpy(ft).to(device))
            per = F.cross_entropy(logits, y, weight=cw, reduction="none") * sw
            loss = per.sum() / (cw[y] * sw).sum()
            opt.zero_grad()
            loss.backward()
            opt.step()
            total += float(loss.detach()) * len(idx)
            wsum += len(idx)
        rec = {"epoch": epoch, "train_loss": total / max(wsum, 1)}
        if split["val"]:
            p = predict_probs(net, split["val"], meta, device=device)
            yv = np.array([classes.index(r["label"]) for r in split["val"]])
            m = metrics([r["label"] for r in split["val"]], [classes[k] for k in p.argmax(1)], p.max(1), classes)
            rec.update({"val_loss": float(-np.log(np.clip(p[np.arange(len(yv)), yv], 1e-9, 1)).mean()),
                        "val_accuracy": m["accuracy"], "val_macro_f1": m["macro_f1"]})
            key = (m["macro_f1"] or 0.0, -rec["val_loss"])
        else:
            key = (epoch, 0)  # no val split: keep the last epoch
        history.append(rec)
        log("  " + ", ".join(f"{k} {v:.4f}" if isinstance(v, float) else f"{k} {v}" for k, v in rec.items()))
        if best_key is None or key > best_key:
            best_key, since = key, 0
            best = {k: v.detach().cpu().clone() for k, v in net.state_dict().items()}
            meta["best_epoch"] = epoch
        else:
            since += 1
            if since >= cfg.patience:
                log(f"  stopped early: no better val macro F1 for {cfg.patience} epochs")
                break
    net.load_state_dict(best)
    buf = io.BytesIO()
    torch.save(best, buf)
    weights = buf.getvalue()
    (out_dir / "model.pt").write_bytes(weights)
    date = datetime.now(timezone.utc).strftime("%Y%m%d")
    meta["model_version"] = cfg.model_version or f"morphology-{date}-{hashlib.sha256(weights).hexdigest()[:8]}"
    meta["metrics"] = {}
    for s in ("val", "test"):
        if split[s]:
            p = predict_probs(net, split[s], meta, device=device)
            pr = prediction_rows([r["particle_ref"] for r in split[s]], [r["label"] for r in split[s]], p, classes,
                                 [{"sample_id": r["sample_id"]} for r in split[s]])
            write_predictions(out_dir / f"predictions_{s}.csv", pr, classes)
            meta["metrics"][s] = metrics([r["label"] for r in pr], [r["pred"] for r in pr],
                                         [float(r["confidence"]) for r in pr], classes)
    meta.update({"n_train": len(split["train"]), "n_val": len(split["val"]), "n_test": len(split["test"]),
                 "left_out_rows_by_split": dropped, "config": asdict(cfg), "torch_version": torch.__version__,
                 "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
    write_json(out_dir / "model.json", meta)
    write_csv(out_dir / "history.csv", history, sorted({k for h in history for k in h}, key=lambda k: k != "epoch"))
    log(f"saved {meta['model_version']} -> {out_dir}")
    return meta


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("dataset")
    ap.add_argument("--out", required=True)
    d = TrainConfig()
    for name in ("epochs", "batch_size", "patience", "crop_size", "min_class_count", "seed"):
        ap.add_argument(f"--{name.replace('_', '-')}", type=int, default=getattr(d, name))
    for name in ("lr", "weight_decay"):
        ap.add_argument(f"--{name.replace('_', '-')}", type=float, default=getattr(d, name))
    ap.add_argument("--backbone", default=d.backbone, choices=["small", "mobilenet_v3_small"])
    ap.add_argument("--pretrained", action="store_true")
    ap.add_argument("--head", default=d.head, choices=["single", "chain", "multitask"])
    ap.add_argument("--device", default=d.device)
    ap.add_argument("--no-class-weights", action="store_true")
    ap.add_argument("--model-version", default="")
    a = ap.parse_args(argv)
    cfg = TrainConfig(epochs=a.epochs, batch_size=a.batch_size, lr=a.lr, weight_decay=a.weight_decay,
                      patience=a.patience, crop_size=a.crop_size, backbone=a.backbone, pretrained=a.pretrained,
                      head=a.head, min_class_count=a.min_class_count, class_weights=not a.no_class_weights,
                      seed=a.seed, device=a.device, model_version=a.model_version)
    train(a.dataset, a.out, cfg)


if __name__ == "__main__":
    main()
