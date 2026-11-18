# Part 10: Model training, retraining and versioning

Training the morphology model (part 5) and keeping it up to date: periodic, manual retraining on corrected labels. A new version only replaces the current one if it does better on a fixed, expert-labelled gold test set, and every version is recorded so past results stay reproducible.

**Method:** a process. Python + PyTorch on a lab computer or free notebooks (Colab, Kaggle). There is no continuous online learning (decided: it risks drift and training on unchecked predictions).

## In → Out

| In | Out |
|---|---|
| The labelled set (part 7) and database snapshots of reviewed labels (part 9) | A trained model exported to ONNX for the browser (part 5 / part 8) |
| Particle crops (part 5, `crop_particle`) | A model version record with its gold-set scores |
| | A go / no-go decision against the current model |

## What exists (November 18, 2026)

The scaffold is built and runs end to end on synthetic particles; it is waiting for real labels.

| File | Does | Needs torch? |
|---|---|---|
| `build_dataset.py` | Crops, labels and shape values from pipeline runs; split by sample; the gold set held out | no |
| `train.py` | Trains the model on crop + shape values + background type; saves weights and the sidecar | yes |
| `evaluate.py` | Accuracy per class, confusion matrix, macro F1, calibration (ECE), from a predictions file | no |
| `infer.py` | Predictions for one split, from a trained folder (torch) or an ONNX file (onnxruntime) | either |
| `export_onnx.py` | ONNX file + JSON sidecar for the browser; checks onnxruntime gives the same answers as torch | yes |
| `gate.py` | Candidate vs current model on the gold set; writes the version record | no (with predictions files) |
| `common.py` | What they share: the model's inputs, the augmentation, label names | no |
| `synthetic.py` | Synthetic labelled runs (sheet photos through the real pipeline), for the tests and a smoke run | no |

The browser side is `web/src/morphology/model.js`: it loads the ONNX file and its sidecar with ONNX Runtime Web and builds the same inputs. It is not wired into the app yet.

### The model

One shared model for the three sheets, with the background type as an input (Drive decision):

- **Image:** the particle's crop on neutral grey (128), resized to `CROP_SIZE` (128 px), as `model_input` in `pipeline/mippr/morphology/model.py`. A small 4-block CNN by default; `--backbone mobilenet_v3_small` uses torchvision's MobileNetV3-Small (`--pretrained` downloads ImageNet weights).
- **Shape values:** `aspect_ratio`, `feret_ratio`, `circularity`, `roundness`, `solidity`, `solidity_subpixel`, `opacity`, `length_mm`, `width_mm`, `area_mm2` (sizes and ratios through log1p), normalised with the train split's mean and spread, missing values set to the mean. Then the background type, one-hot. The crop loses the true size when it is resized, so the size comes in here.
- **Fused:** image and shape branches are joined and a small head gives one score per class. Softmax gives the confidence and the runner-up.
- **Classes:** whatever the train split has, in the order of `MORPHOLOGY_CLASSES`; "other" and "can't tell" labels are left out. Nothing is fiber-specific (fibers are on hold). Rubbery fragment is its own class if the labels have it.
- **Training:** augmentation as decided (any rotation, flips, small perspective changes, scaling limited to ±10%, brightness ±15%, white balance ±4% per channel; no hue shifts), class weights against imbalance, community labels weighted 0.5, AdamW, early stopping on the validation macro F1.
- **Version:** `morphology-<date>-<first 8 of the weights' sha256>`, recorded with the dataset's manifest hash in the sidecar.
- **Hook for open question 5:** `--head chain` / `--head multitask` are reserved in `train.make_net` for the classifier chain vs multi-task comparison; only `single` is built.

### The sidecar (`morphology.onnx.json`)

Everything the browser needs to build the inputs and read the output: `classes`, `crop_size`, `grey`, `image_mean` / `image_std`, `features` (name, transform, mean, std), `backgrounds`, `model_version`, `manifest_sha256`, the val and test metrics, the training settings and the torch / onnxruntime parity check.

## How to run

Install once (Python 3.12 or 3.13): `pip install -r training/requirements.txt` (see the file for the smaller CPU-only torch).

```bash
# 1. Dataset: pipeline runs (particles.csv + crops/) and labels
python training/build_dataset.py --runs results/batch1 results/sheet_check_out \
    --labels advisor_labels.csv --gold gold.txt --keep-splits datasets/previous/manifest.json \
    --out datasets/2027-01

# 2. Train (checks val each epoch, keeps the best)
python training/train.py datasets/2027-01 --out models/candidate

# 3. Look at it (val while developing; test once at the end)
python training/evaluate.py models/candidate/predictions_val.csv

# 4. Export for the browser
python training/export_onnx.py models/candidate --out models/candidate/morphology.onnx --dataset datasets/2027-01

# 5. Gate against the model in use, on the gold set; record the version
python training/gate.py --candidate models/candidate/morphology.onnx --current models/current/morphology.onnx \
    --dataset datasets/2027-01 --out models/candidate/version.json --registry models/model_versions.json
```

Labels for step 1 come from:

- **Reviewed rows:** `review_status` confirmed or corrected; the label is `morphology_label` (the corrected value), the labeller `reviewed_by` and `reviewer_role`. A confirmed row counts as the reviewer accepting its morphology label.
- **Box-label sheets** (`validation/templates/advisor_labels.csv`): joined to the run's rows by photo (`photo_file`, its stem, or `picture_label`) and box. The lab's names are mapped as in validation (`lab_sheets.lab_shape`: Fibers → fiber, Sphere → pellet, ...). `--labels-role` says whether they are expert (default) or community.

Rejected rows are left out, so the originals replaced by a split or merge never train; the new rows are used once they have a crop. Two experts who disagree leave the particle out. A box with several kept blobs is left out of the box-label join, since it is unclear which one the label means. `manifest.json` counts everything left out and why.

**Splits** are by sample, never by photo or particle. `--keep-splits` keeps each sample's split from the previous dataset, so a test sample never moves into training later. The **gold list** (`gold.txt`) holds one `particle_ref` or `sample_id:<id>` per line; those particles get split `gold` and the rest of their sample `excluded`, and `gate.py` checks none of them leaked into train, val or test.

**Gate:** accepted only if the gold macro F1 is not worse than the current model's and no class's recall drops by more than 0.05 (both settable). With no current model, `--min-macro-f1` decides. The record has the `model_versions` table's fields (`version`, `kind`, `trained_on`, `gold_set_score`, `approved`, `created_at`) plus the reasons and both models' gold scores.

### On Colab or Kaggle

Build the dataset on the lab computer (it copies the crops into the dataset folder), zip the folder, and upload it with the repo's `training/`, `pipeline/mippr/` and `validation/lab_sheets.py`. In the notebook: `pip install onnx onnxruntime` (torch is already there), then steps 2–5 with `--device auto` to use the GPU. Download the model folder and the ONNX file with its sidecar.

### Smoke run

```bash
python training/synthetic.py --out /tmp/smoke --photos 6 --per-class 12
python training/build_dataset.py --runs /tmp/smoke/runs --labels /tmp/smoke/labels.csv --gold /tmp/smoke/gold.txt --out /tmp/smoke/dataset
python training/train.py /tmp/smoke/dataset --out /tmp/smoke/model --epochs 15
```

On November 18, 2026: 6 synthetic photos (white and black grids), 216 particles, all matched to their labels (pellet, fragment, rubbery fragment: 108 train, 36 val, 36 test, 36 gold). 15 epochs on a CPU took 17 s; val macro F1 reached 1.0 at epoch 6, test 1.0 (ECE 0.006). The ONNX file gave the same probabilities as torch within 1.2e-7. `model.js` with ONNX Runtime Web 1.20.1 in Node, on 8 test crops, gave the same labels as torch, probabilities within 3.3e-4 (from the one-grey-level resize difference). The gate accepted the 15-epoch model over a 2-epoch one and rejected the reverse. These particles are easy on purpose: this checks the plumbing, not the model.

### Tests

```bash
cd training && python -m pytest -q
```

`test_build_dataset.py`, `test_common.py` and `test_evaluate_gate.py` need no torch. `test_torch_pipeline.py` runs the whole chain on a tiny synthetic set and is skipped without torch (and its ONNX part without onnx / onnxruntime). The training tests are not in CI yet, and torch stays out of CI.

## To build

- [ ] The gold test set: expert-labelled, fixed, never used for training (built in part 7)
- [ ] The first model (v3) on the lab's labelled particles re-photographed on the three sheets: fragment, rubbery fragment; plus new labels for film and foam. Background type is an input (one shared model, Drive decision). Fibers are on hold (advisor, November 18).
- [x] Augmentation: rotations, flips, small perspective changes, mild brightness and white-balance jitter. No hue shifts (colour is a label); limit scaling, since size matters. (`common.augment`)
- [x] The retraining routine as scripts: build the dataset, train, evaluate, export, gate, record the version (this folder)
- [ ] The retraining routine in practice: export a database snapshot (part 9) to run folders, run it, publish the version
- [ ] Compare a classifier chain with one multi-task model (open question 5; `--head` hook)
- [ ] Vendor ONNX Runtime Web in `web/vendor/` (the site only loads scripts from itself) and wire `model.js` into the pipeline with `combine` (model.py)
- [ ] Where training runs (open question 8) and who runs it after the practicum (open question 7)
- [ ] Publish models and datasets (GitHub releases, Hugging Face or Zenodo with a DOI per version)

## Watch for

Labels from community reviewers vary more than expert labels. They are weighted 0.5 in training, and a gold particle with a community label is reported as a warning.

Crops are not redrawn when an outline is edited (`crop_file`), so an edited row's crop can differ from its measured outline; `outline_edited` is kept in the manifest to check this.
