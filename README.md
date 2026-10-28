# MIPPR

Microplastic Image Processing Pipeline for Research.

Manual classification of microplastics larger than 500 µm (color, morphology, size) is slow, hard to standardize, and depends on who is looking. MIPPR is a batch image-processing pipeline that classifies and measures particles the same way every time, with an open-source web app planned if feasible.

## Plan

- [Classification spec](docs/CLASSIFICATION_SPEC.md): size rule, classes, review flags and output columns (issue 1)
- [Project context and decisions](CLAUDE.md): goal, scope, imaging plan, free browser-based stack, release plan, open questions (current source of truth, spec v0.4)
- [Pipeline plan and checklist](docs/PIPELINE.md): every stage, task, input, output and risk
- [Interactive tracker](docs/pipeline-tracker.html): the same plan as a checkbox page (download and open in a browser)

## Stages

1. Define scope and classes
2. Standardize image capture
3. Build the labeled dataset
4. Preprocess images
5. Segment particles
6. Measure size and shape
7. Classify color and morphology
8. Validate against people
9. Batch run and outputs
10. Open-source web app (if feasible)
11. Document and release

## Status

Python prototype of segmentation and measurement in [prototype/](prototype/README.md). It finds all 24 particles in the lab's sample photo and matches the lab's ImageJ measurements to within 2% (median). Next: validate against hand measurements, then port to OpenCV.js for the v1 browser app.
