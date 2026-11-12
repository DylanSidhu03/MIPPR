# Part 10: Model training, retraining and versioning

Training the morphology model (part 5) and keeping it up to date: periodic, manual retraining on corrected labels. A new version only replaces the current one if it does better on a fixed, expert-labelled gold test set, and every version is recorded so past results stay reproducible.

**Method:** a process. Python + PyTorch on a lab computer or free notebooks (Colab, Kaggle). There is no continuous online learning (decided: it risks drift and training on unchecked predictions).

## In → Out

| In | Out |
|---|---|
| The labelled set (part 7) and database snapshots of reviewed labels (part 9) | A trained model exported to ONNX for the browser (part 5 / part 8) |
| Particle crops (part 5, `crop_particle`) | A model version record with its gold-set scores |
| | A go / no-go decision against the current model |

## Planned pieces

| File | Does |
|---|---|
| `build_dataset.py` | Crops and labels from photos on the printed sheets: the lab's labelled particles re-photographed on the sheets (labels carried over by well), and database snapshots; split by sample; the gold set is held out and never trained on |
| `train.py` | Train on crops + shape values + background type; compare a classifier chain with one multi-task model |
| `evaluate.py` | Accuracy per class, confusion matrix, calibration of the confidences |
| `export_onnx.py` | Export for ONNX Runtime Web; check the browser gives the same answers |
| `gate.py` | Compare a candidate with the current model on the gold set; record the version |

All are stubs today.

## To build

- [ ] The gold test set: expert-labelled, fixed, never used for training (built in part 7)
- [ ] The first model (v3) on the lab's labelled particles re-photographed on the three sheets: fragment, rubbery fragment, fiber; plus new labels for film and foam. Background type is an input (one shared model, Drive decision).
- [ ] Augmentation: rotations, flips, small perspective changes, mild brightness and white-balance jitter. No hue shifts (colour is a label); limit scaling, since size matters.
- [ ] The retraining routine: export a snapshot, build the dataset, train, evaluate, gate, publish the version
- [ ] Where training runs (open question 8) and who runs it after the practicum (open question 7)
- [ ] Publish models and datasets (GitHub releases, Hugging Face or Zenodo with a DOI per version)

## Watch for

Labels from community reviewers vary more than expert labels. Weight them, or keep them out of the gold set.
