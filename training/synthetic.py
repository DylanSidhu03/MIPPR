"""Part 10: synthetic labelled runs, for the tests and the end-to-end smoke run (no real labels yet).

    python training/synthetic.py --out SMOKE_DIR [--photos 6] [--per-class 12]
    # then: build_dataset.py --runs SMOKE_DIR/runs --labels SMOKE_DIR/labels.csv --gold SMOKE_DIR/gold.txt ...

Each photo is a synthetic sheet photo (pipeline/mippr/capture/synthetic.py) with particles drawn in
chosen boxes and run through the normal pipeline (mippr.cli.run_grid), so the crops and shape values
are the real thing. The label is what was drawn: pellet (disc), fragment (long rectangle) and
rubbery_fragment (dark, squat rectangle). Easy on purpose: this checks the plumbing, not the model.
Every photo is its own sample. Box labels go to labels.csv (the advisor_labels.csv layout); the
last photo's particles are the gold list.
"""
import argparse
import csv
import sys
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import common  # noqa: E402,F401  (puts pipeline/ on the path)
from mippr.capture.sheet import Layout  # noqa: E402
from mippr.capture.synthetic import draw_particle, photograph, sheet_bgr  # noqa: E402
from mippr.cli import run_grid  # noqa: E402

DPI = 300
# class: (shape, size range mm, aspect range, colour on light sheets, colour on the black grid)
KINDS = {
    "pellet": ("disc", (1.5, 3.0), (1.0, 1.0), (200, 90, 40), (235, 235, 235)),
    "fragment": ("rect", (2.5, 4.5), (1.7, 2.4), (40, 120, 220), (60, 210, 230)),
    "rubbery_fragment": ("rect", (2.0, 3.5), (1.1, 1.5), (35, 35, 35), (150, 150, 150)),
}


def make_photo(path, background, items, seed):
    """Draw `items` [(box, kind, size_mm, aspect, angle)] and photograph the sheet."""
    lay = Layout(background, "letter")
    img = sheet_bgr(lay, DPI)
    for box, kind, size, aspect, angle in items:
        shape, _, _, light, dark = KINDS[kind]
        draw_particle(img, lay, DPI, box, shape, size, dark if background == "black_grid" else light,
                      angle=angle, aspect=aspect)
    cv2.imwrite(str(path), photograph(img, seed=seed, k1=-0.02, out_width=2400))


def make_runs(out_dir, n_photos=4, per_class=4, seed=0, backgrounds=("white_grid", "black_grid")):
    """Photos, pipeline runs and labels under out_dir; returns (runs_dir, labels_csv, gold_txt)."""
    out = Path(out_dir)
    (out / "photos").mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    lay = Layout()
    boxes = [lay.box_label(r, c) for r in range(1, lay.rows - 1) for c in range(1, lay.cols - 1)]
    labels, gold = [], []
    for n in range(n_photos):
        bg = backgrounds[n % len(backgrounds)]
        picks = rng.choice(len(boxes), per_class * len(KINDS), replace=False)
        items = []
        for k, i in enumerate(picks):
            kind = list(KINDS)[k % len(KINDS)]
            _, (s0, s1), (a0, a1), _, _ = KINDS[kind]
            items.append((boxes[i], kind, float(rng.uniform(s0, s1)), float(rng.uniform(a0, a1)),
                          float(rng.uniform(0, 180))))
        name = f"syn{n + 1:02d}_{bg}.jpg"
        make_photo(out / "photos" / name, bg, items, seed * 100 + n)
        sample = f"SYN{n + 1:02d}"
        run_grid(out / "photos" / name, out / "runs" / Path(name).stem, sample_id=sample, photo=1)
        for box, kind, *_ in items:
            labels.append({"photo": name, "sheet": bg, "box": box, "morphology": kind, "labeller": "synthetic"})
            if n == n_photos - 1:
                gold.append(f"{sample}-P01-{box}")
    with open(out / "labels.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["photo", "sheet", "box", "morphology", "colour", "labeller", "notes"],
                           extrasaction="ignore")
        w.writeheader()
        w.writerows(labels)
    (out / "gold.txt").write_text("\n".join(gold) + "\n")
    return out / "runs", out / "labels.csv", out / "gold.txt"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", required=True)
    ap.add_argument("--photos", type=int, default=6)
    ap.add_argument("--per-class", type=int, default=12)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args(argv)
    runs, labels, gold = make_runs(a.out, a.photos, a.per_class, a.seed)
    print(f"runs: {runs}\nlabels: {labels}\ngold: {gold}")


if __name__ == "__main__":
    main()
