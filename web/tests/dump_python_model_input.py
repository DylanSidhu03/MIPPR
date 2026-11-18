"""Fixtures for the morphology-model input test: training/common.py's prepare_image (= model_input) and
feature_vector on small crops and rows.

Writes web/tests/fixtures/model_input.json:
- images: RGBA crops (shrunk, enlarged, an integer factor, and a non-square edge crop) with the
  RGB size x size image Python builds from each (size 16, to keep the file small);
- features: a sidecar's feature normalisation and rows (with missing and odd values) with Python's vectors.

    .venv/bin/python web/tests/dump_python_model_input.py
"""
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "training"))
from common import BACKGROUNDS, FEATURES, GREY, feature_stats, feature_vector, prepare_image  # noqa: E402

SIZE = 16


def crop(rng, w, h):
    """A blob-like RGBA crop: random colours, alpha 255 inside an ellipse, a few half-transparent edge pixels."""
    yy, xx = np.mgrid[0:h, 0:w]
    r = ((xx - w / 2 + 0.5) / (w * 0.4)) ** 2 + ((yy - h / 2 + 0.5) / (h * 0.4)) ** 2
    a = np.where(r < 1, 255, np.where(r < 1.3, 128, 0)).astype(np.uint8)
    rgb = rng.integers(0, 256, (h, w, 3), dtype=np.uint8)
    return np.dstack([rgb, a])


def main():
    rng = np.random.default_rng(7)
    images = []
    for w, h in ((10, 10), (40, 40), (32, 32), (23, 37), (12, 30), (16, 16)):
        rgba = crop(rng, w, h)
        bgra = np.dstack([rgba[..., 2::-1], rgba[..., 3:]])
        out = prepare_image(bgra, SIZE, GREY)[..., ::-1]  # BGR -> RGB
        images.append({"width": w, "height": h, "rgba": rgba.ravel().tolist(), "size": SIZE,
                       "rgb": out.ravel().tolist()})
    rows = [
        {"aspect_ratio": "1.2", "feret_ratio": "1.4", "circularity": "0.8", "roundness": "0.75", "solidity": "0.93",
         "solidity_subpixel": "0.97", "opacity": "0.9", "length_mm": "2.5", "width_mm": "1.8", "area_mm2": "3.4",
         "background_type": "white_grid"},
        {"aspect_ratio": "3.1", "feret_ratio": "4.2", "circularity": "0.3", "roundness": "0.31", "solidity": "0.7",
         "solidity_subpixel": "0.72", "opacity": "0.4", "length_mm": "4.9", "width_mm": "1.1", "area_mm2": "4.0",
         "background_type": "checkerboard"},
        {"aspect_ratio": "1.0", "feret_ratio": "1.05", "circularity": "0.95", "roundness": "0.98", "solidity": "0.95",
         "solidity_subpixel": "1.0", "opacity": "1.0", "length_mm": "1.6", "width_mm": "1.5", "area_mm2": "1.9",
         "background_type": "black_grid"},
    ]
    stats = feature_stats(rows, FEATURES)
    cases = rows + [
        {**rows[0], "width_mm": "", "opacity": "nan", "background_type": "black_grid"},  # missing -> 0
        {**rows[1], "length_mm": "-0.5", "background_type": "unknown"},  # log1p of a negative is clamped; no one-hot
    ]
    sidecar = {"features": stats, "backgrounds": BACKGROUNDS}
    feats = [{"row": r, "vector": [float(v) for v in feature_vector(r, stats, BACKGROUNDS)]} for r in cases]
    out = ROOT / "web" / "tests" / "fixtures" / "model_input.json"
    out.write_text(json.dumps({"grey": GREY, "images": images, "sidecar": sidecar, "features": feats}) + "\n")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
