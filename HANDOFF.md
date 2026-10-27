# Handoff for the Code session

Goal: get this folder onto https://github.com/DylanSidhu03/MIPPR (currently empty) so a cloud Claude session can work on it.

## Project in one paragraph
MIPPR automates classification and measurement of microplastics larger than 500 µm (color, morphology, size) from photos, replacing subjective hand-picking. It is a batch image-processing pipeline, with an open-source web app if feasible. Status: planning, no code yet.

## What is in this folder
- README.md: project overview
- docs/PIPELINE.md: full 11-stage plan with task checklists (source of truth)
- docs/pipeline-tracker.html: interactive checkbox version of the same plan
- .github/ISSUE_TEMPLATE/task.md: issue template
- scripts-create-issues.sh: creates one GitHub issue per stage (needs gh auth)
- .gitignore

## Do now (in order)
1. cd into this folder. Check for secrets or junk (.env, keys, credentials, large files, .DS_Store). Report anything sensitive. .gitignore already covers common cases.
2. git init if needed. Remote origin = https://github.com/DylanSidhu03/MIPPR.git (show any existing origin before changing it).
3. Commit everything as "Initial commit", rename branch to main, git push -u origin main. If rejected, explain why; never force-push.
4. Confirm the push and list top-level files uploaded.
5. Optional: run ./scripts-create-issues.sh to open the stage issues. Optionally publish docs/pipeline-tracker.html with GitHub Pages.

## Next project steps (from docs/PIPELINE.md)
1. Define scope and classes: size rule, morphology and color class lists, "not plastic" handling, output columns.
2. Standardize image capture: setup, background, scale and color reference, px/µm calibration, pilot batch of 50-100 particles.
3. Build labeled dataset: 300+ labeled particles, second labeler on 20%, measure agreement, split by sample.
4. Preprocess: flat-field, white balance, LAB color, scale detection.
5. Segment: classical baseline, then Cellpose/SAM/U-Net; handle touching particles and fibers.
6. Measure: area, Feret axes, aspect ratio, skeleton length for fibers, 500 µm cutoff, compare to manual.
7. Classify color and morphology with confidence scores and a review list.
8. Validate on a held-out test set against human agreement; test on a second setup.
9. Batch CLI with CSV, summary and QC overlays; README.
10. Decision point, then web app (if feasible).
11. Document and release.

## First coding milestone suggestion
Stages 1-2 need no code: write the classification spec and shoot the pilot batch. Code starts at stage 4/5 with a classical-segmentation baseline in Python (OpenCV + scikit-image) on the pilot images.
