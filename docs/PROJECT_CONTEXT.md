# Microplastics Auto Imaging: project context

Moore Institute for Plastic Pollution Research (MIPPR) and USF practicum project.
Living spec (planning page, kept up to date in chat): https://claude.ai/artifact/21V9QiiwUaRm454CdPMypP
Spec version at time of writing: 0.3 (October 27, 2026)

This file supersedes the stage list in [PIPELINE.md](PIPELINE.md) where they differ (stack, release plan, stage order).

## The problem

Microplastics larger than 500 µm are currently classified by hand: a person looks at each particle and decides its color, morphology, and size, then measures it in ImageJ. This is slow, labor-intensive, and hard to standardize, because results depend on who is doing the picking and how they judge color and shape.

## The goal

Build a free, open-source web app that takes photos of hand-picked particles and returns standardized measurements and classifications (color, morphology), with batch processing. Users are lab researchers and community scientists.

Scope boundary: the app automates measurement and visual classification of particles that have already been hand-picked. It does not decide whether something is plastic. Polymer identification would require spectroscopy (FTIR or Raman) and is out of scope.

## How the images are produced (existing lab workflow)

1. Samples arrive.
2. Sieved and prepped.
3. Density or chemical separation.
4. Size fractionation (>500 µm, and down to ~20 µm; only the >500 µm fraction is in scope).
5. Particles are hand-picked and photographed on a checkerboard / grid background.
6. Measured manually in ImageJ.

## Existing material

- GitHub repo: https://github.com/Moore-Institute-4-Plastic-Pollution-Res/fragment_area
  Early prototype, no README. Files include `template.jpg` (empty checkerboard), `particle.jpg` (checkerboard with particles), `difference.py` producing `diff.jpg`, `checkboard.py`, `checkerboard_particles.ijm`, `image_crop.py`, `image.py`. The approach appears to be background subtraction: photograph the empty template, photograph it with particles, align/crop both, and subtract to isolate particles from the grid.
- ImageJ macro (current semi-automated measurement), from https://forum.image.sc/t/removing-gridlines/114824 :

```
original=getTitle();
run("Duplicate...", "title=dark");
run("8-bit");
run("Duplicate...", "title=light");
setAutoThreshold("Default");
run("Convert to Mask");
run("Analyze Particles...", "size=2-200 add clear");
selectImage("dark");
setAutoThreshold("Default dark");
run("Convert to Mask");
run("Analyze Particles...", "size=2-200 add");
close("dark");
close("light");
selectWindow(original);
roiManager("Show All without labels");
```

  It converts to 8-bit and thresholds twice: once for dark particles on light squares, once ("Default dark") for light particles on dark squares, adding detected particles (size filter 2–200 in the image's units) to the ROI Manager. The gridlines interfering with thresholding are a known pain point.
- Commercial benchmark: Saturna by Ocean Diagnostics (https://oceandiagnostics.com/microplastics-imaging-technology). Closed source, paid, hardware-locked, for particles >400 µm. Uses controlled LED lighting and a QR-code background as the scale reference. Its output metrics are a good target spec: max width, 2D area, convex area, perimeter, convex perimeter, circular equivalent diameter, bounding box width/height, aspect ratio, circularity, solidity, mean HSV and BGR color. This project is meant to be a free alternative that works with ordinary cameras.

## Pipeline (stages and status)

1. **Sample prep**: existing lab process (above).
2. **Imaging protocol**: OPEN. Need a standard background, scale reference in every frame, fixed lighting and overhead angle, ideally phone-friendly. Options: keep checkerboard, add an empty-template photo for subtraction, or switch to a plain background with a printed scale reference. Output: raw photo + metadata (lab, camera, background, date).
3. **Segmentation**: PROTOTYPE. Find every particle, produce one mask per particle, and a crop of each particle with background blanked out. Must handle gridlines bleeding into outlines, touching particles, and translucent films. Errors here propagate everywhere.
4. **Measurement**: DECIDED. Deterministic geometry from masks, not a learned model, for exact reproducibility. Size/shape: area, perimeter, max length (Feret), min width, circular equivalent diameter, bounding box, aspect ratio, circularity, solidity, convex area/perimeter. Color values: mean and spread of RGB, HSV, Lab within the mask. Convert pixels to real units using the scale reference. Output: one row per particle.
5. **Classification**: PROPOSED.
   - Color: likely rule-based binning of HSV/Lab into defined categories (deterministic, explainable).
   - Morphology (fragment, fiber, film, foam, pellet): image model (CNN) on per-particle crops, optionally also fed the measurement row.
   - Augmentation: rotations, flips, small shear/perspective warps, mild brightness/white-balance jitter. No hue shifts (color is a label); limit scaling if size affects class.
   - Multiple models with correlations between characteristics (e.g., white foams, clear films). Two designs to compare: (a) a classifier chain where color output, as probabilities, feeds the morphology model, trained on out-of-fold predictions to avoid leakage; (b) one multi-task network with a shared backbone and a separate head per characteristic.
   - Every prediction includes a confidence score and the model version.
6. **Database**: PROPOSED. Single source of truth: images + metadata; particles (mask, crop, measurements); labels (who, when, expert vs community); predictions + model version. Free version: versioned dataset files (CSV or Parquet plus crop images) in a public repository, not a hosted database server.
7. **Review and retraining**: PROPOSED. Not continuous online learning (risks drift, catastrophic forgetting, and training on unchecked predictions). Instead:
   - Active learning: low-confidence predictions are routed to a human first.
   - Periodic retraining on the full dataset, run manually.
   - A fixed expert-labeled gold test set, never used for training, gates whether a new model replaces the current one.
   - Every model is versioned so past results stay reproducible.
8. **Outputs and web app**: PROPOSED. Annotated images with each particle outlined and numbered; CSV with one row per particle (measurements, color, morphology, confidence, model version); a review screen to reject false detections or correct classes before export.

## Decisions log

- Measurements are deterministic geometry; ML only where judgment is needed.
- Periodic, gated retraining instead of continuous online updates.
- Separate predictions per characteristic, using correlations between them.
- The deliverable is a usable web app, released in stages: measurement first, ML later.
- Everything is free to use and free to run (no paid servers or services). Ease of building/maintaining is secondary to zero cost.

## Free technical stack (decided)

| Piece | Choice |
|---|---|
| Hosting | Static site on GitHub Pages from a public repo |
| Image processing | OpenCV.js in the browser |
| Model inference | Model exported to ONNX, run with ONNX Runtime Web in the browser |
| Model training | Python + PyTorch on a lab computer, or free notebooks (Google Colab, Kaggle) |
| Publishing models/data | GitHub releases, Hugging Face Hub, or Zenodo (citable DOI per dataset version) |
| Collecting labels | Users export corrected labels as a file and submit it; team reviews and merges into the dataset |

Implications: all processing is client-side, so user photos never leave their computer. No backend, no live shared database, no server-side scheduled jobs. Large batches are limited by the user's machine. Do not depend on free tiers of hosted services, since their limits can change. Prototyping segmentation and measurement in Python (OpenCV / scikit-image) is fine, but the shipped app must run in the browser, so prefer algorithms that port cleanly to OpenCV.js.

## Release plan

- **v1**: upload, segmentation, measurement, outline review/correction, CSV export. Replaces manual ImageJ measuring.
- **v2**: rule-based color categories.
- **v3**: morphology model with confidence scores, trained on labels collected in v1 and v2.
- **v4**: label contributions and gated retraining workflow.

Each release should be usable on its own. Corrections users make in v1/v2 become training data for v3.

## Users

- Lab researchers: batch upload, accurate measurements, CSV export compatible with existing workflows, fast correction.
- Community scientists: clear photo instructions, phone camera support, in-app warnings when a photo is blurry, too dark, or missing the scale reference.

## Open questions

1. Which background and scale reference can the lab standardize on?
2. Exact list of characteristics to classify. Is "texture" (e.g., smooth vs weathered surface) separate from morphology in the lab's protocol?
3. Defined color categories and morphology classes.
4. Does a labeled set of particle photos already exist from past hand-classification, or must it be built?
5. Chained models or one multi-task model?
6. How close to hand measurements must results be to count as validated?
7. Who maintains the app, reviews contributed labels, and runs retraining after the practicum?
8. Where is training run: a lab GPU machine or free notebooks?
9. Data license and consent terms for contributed photos and labels.
10. Should the stack align with the Moore Institute's other open-source tools (e.g., Open Specy) so the lab can maintain it?

## Suggested first steps for a coding session

1. Read through the `fragment_area` repo and get the template-difference approach running on `template.jpg` and `particle.jpg`.
2. Build a Python segmentation prototype that produces clean per-particle masks on the checkerboard, and compare it against the ImageJ macro's output.
3. Implement the measurement functions from masks with a pixel-to-mm scale, and validate them against hand measurements.
4. Then port the working approach to OpenCV.js for the v1 browser app.

Status of these steps: 1 and 2 done, 3 done except validation against hand measurements. See [prototype/README.md](../prototype/README.md).
