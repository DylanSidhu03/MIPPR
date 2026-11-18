"""Part 10: what the dataset builder, the trainer and the exporter share (no torch here).

- The model's inputs: the crop on grey at the model's size (the same as
  pipeline/mippr/morphology/model.py `model_input`, and web/src/morphology/model.js), the shape
  values, transformed and normalised, and the background type, one-hot.
- The augmentation (rotations, flips, small perspective, limited scaling, mild brightness and
  white-balance jitter; no hue shifts, since colour is a label).
- Label names and file helpers.
"""
import csv
import hashlib
import json
import math
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT / "pipeline", ROOT / "validation"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from mippr.crops import crop_box  # noqa: E402
from mippr.morphology.model import CROP_SIZE  # noqa: E402
from mippr.morphology.rules import MORPHOLOGY_CLASSES  # noqa: E402

GREY = 128  # the neutral grey the crop is put on (model_input)
BACKGROUNDS = ["white_grid", "black_grid", "checkerboard"]  # one-hot, in this order
# Shape values the model sees (docs/OUTPUT_CSV.md 4.3-4.6), with a transform before normalising:
# log1p for the long-tailed sizes and ratios, none for values already in 0-1.
FEATURES = [
    ("aspect_ratio", "log1p"),
    ("feret_ratio", "log1p"),
    ("circularity", "none"),
    ("roundness", "none"),
    ("solidity", "none"),
    ("solidity_subpixel", "none"),
    ("opacity", "none"),
    ("length_mm", "log1p"),
    ("width_mm", "log1p"),
    ("area_mm2", "log1p"),
]
# The image is fed as RGB in 0-1, then (x - mean) / std per channel. Kept in the model's sidecar.
IMAGE_MEAN = [0.5, 0.5, 0.5]
IMAGE_STD = [0.25, 0.25, 0.25]
NOT_TRAINED_ON = ("other", "unknown", "")  # labels that say "can't tell" are left out by default


def normalise_label(name):
    """The app's morphology class for a label (the app's own names or the lab's), or None.

    Uses validation/lab_sheets.py's mapping, so the lab's names (Fibers, Sphere, Rubbery ...) mean
    the same here as in the validation reports. "other" stays "other" (left out by default)."""
    s = " ".join(str(name or "").replace("_", " ").replace("-", " ").lower().split())
    if not s:
        return None
    if s.replace(" ", "_") in MORPHOLOGY_CLASSES:
        return s.replace(" ", "_")
    try:
        from lab_sheets import lab_shape
        return lab_shape(s)
    except ImportError:  # e.g. training/ copied to a notebook without validation/
        return None


# ---- images ----------------------------------------------------------------------------------

def read_crop(path):
    """A crop PNG (crops/<particle_ref>.png) as BGRA uint8; crops without alpha are taken as opaque."""
    img = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if img is None:
        raise FileNotFoundError(path)
    if img.ndim == 2:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    if img.shape[2] == 3:
        img = np.dstack([img, np.full(img.shape[:2], 255, np.uint8)])
    return img


def flatten_on_grey(bgra, grey=GREY):
    """The crop on neutral grey, as model_input does (same arithmetic, so the same bytes)."""
    a = bgra[..., 3:4] / 255.0
    return (bgra[..., :3] * a + grey * (1 - a)).astype(np.uint8)


def prepare_image(bgra, size=CROP_SIZE, grey=GREY):
    """BGR uint8 size x size: equal to model_input(img, mask, size)[0] for that particle's crop."""
    return cv2.resize(flatten_on_grey(bgra, grey), (size, size), interpolation=cv2.INTER_AREA)


def image_array(bgr, mean=IMAGE_MEAN, std=IMAGE_STD):
    """float32 3 x H x W, RGB, normalised: the model's `image` input for one particle."""
    rgb = bgr[..., ::-1].astype(np.float32) / 255.0
    return ((rgb - np.float32(mean)) / np.float32(std)).transpose(2, 0, 1).copy()


# ---- augmentation ----------------------------------------------------------------------------

AUGMENT_DEFAULTS = {
    "rotate": True,          # any angle (particles have no up)
    "flip": True,            # mirror half the time
    "perspective": 0.04,     # corners moved by up to this share of the side
    "scale": 0.10,           # limited: 0.9-1.1 (size matters; the shape values carry the true size)
    "brightness": 0.15,      # x 0.85-1.15
    "white_balance": 0.04,   # per-channel gain x 0.96-1.04, mean kept: mild, not a hue shift
}


def augment(bgra, rng, cfg=None):
    """A randomly changed copy of a BGRA crop, framed again like a real crop (crops.crop_box).

    The particle is padded with transparent pixels before it is turned, so nothing is cut off, and
    the transparent background stays transparent (it becomes grey when flattened). No hue shift."""
    cfg = {**AUGMENT_DEFAULTS, **(cfg or {})}
    h, w = bgra.shape[:2]
    pad = int(math.ceil(0.5 * max(h, w)))
    big = cv2.copyMakeBorder(bgra, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=(0, 0, 0, 0))
    H, W = big.shape[:2]
    c = np.float32([W / 2, H / 2])
    angle = rng.uniform(0, 360) if cfg["rotate"] else 0.0
    s = rng.uniform(1 - cfg["scale"], 1 + cfg["scale"]) if cfg["scale"] else 1.0
    M = np.vstack([cv2.getRotationMatrix2D(tuple(map(float, c)), angle, s), [0, 0, 1]])
    if cfg["flip"] and rng.random() < 0.5:
        M = np.array([[-1, 0, W], [0, 1, 0], [0, 0, 1]], float) @ M
    if cfg["perspective"]:
        src = np.float32([[0, 0], [W, 0], [W, H], [0, H]])
        dst = (src + rng.uniform(-1, 1, (4, 2)) * cfg["perspective"] * max(h, w)).astype(np.float32)
        M = cv2.getPerspectiveTransform(src, dst) @ M
    out = cv2.warpPerspective(big, M, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT,
                              borderValue=(0, 0, 0, 0))
    ys, xs = np.nonzero(out[..., 3] > 0)
    if len(xs) == 0:
        return bgra.copy()
    x0, y0, x1, y1 = crop_box(xs.min(), ys.min(), xs.max() - xs.min() + 1, ys.max() - ys.min() + 1, out.shape[:2])
    out = out[y0:y1, x0:x1].astype(np.float32)
    gain = rng.uniform(1 - cfg["brightness"], 1 + cfg["brightness"]) if cfg["brightness"] else 1.0
    if cfg["white_balance"]:
        wb = rng.uniform(1 - cfg["white_balance"], 1 + cfg["white_balance"], 3)
        wb /= wb.mean()
    else:
        wb = np.ones(3)
    out[..., :3] *= gain * wb
    return np.clip(out, 0, 255).astype(np.uint8)


# ---- shape values ----------------------------------------------------------------------------

def _num(v):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return math.nan
    return x if math.isfinite(x) else math.nan


def _transform(x, how):
    if math.isnan(x):
        return math.nan
    if how == "log1p":
        return math.log1p(max(x, 0.0))
    return x


def feature_stats(rows, features=FEATURES):
    """[{name, transform, mean, std}] from the training rows only (never val, test or gold)."""
    out = []
    for name, how in features:
        vals = np.array([_transform(_num(r.get(name)), how) for r in rows], float)
        vals = vals[~np.isnan(vals)]
        mean = float(vals.mean()) if len(vals) else 0.0
        std = float(vals.std()) if len(vals) > 1 else 1.0
        out.append({"name": name, "transform": how, "mean": mean, "std": std if std > 1e-6 else 1.0})
    return out


def feature_vector(row, stats, backgrounds=BACKGROUNDS):
    """float32 [len(stats) + len(backgrounds)]: normalised shape values (missing -> 0, the training
    mean) and the background type one-hot (all zero if unknown)."""
    v = []
    for f in stats:
        x = _transform(_num(row.get(f["name"])), f["transform"])
        v.append(0.0 if math.isnan(x) else (x - f["mean"]) / f["std"])
    bg = row.get("background_type", "")
    v += [1.0 if bg == b else 0.0 for b in backgrounds]
    return np.array(v, np.float32)


def feature_names(stats, backgrounds=BACKGROUNDS):
    return [f["name"] for f in stats] + [f"background={b}" for b in backgrounds]


# ---- files -----------------------------------------------------------------------------------

def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_csv(path):
    with open(path, newline="", encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def write_csv(path, rows, columns):
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=columns, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def write_json(path, data):
    Path(path).write_text(json.dumps(data, indent=2, sort_keys=False) + "\n")


def read_manifest(dataset_dir):
    """(rows, info) of a dataset built by build_dataset.py; crop paths are made absolute."""
    d = Path(dataset_dir)
    rows = read_csv(d / "manifest.csv")
    for r in rows:
        r["crop_path"] = str(d / r["crop"])
    info = json.loads((d / "manifest.json").read_text())
    return rows, info
