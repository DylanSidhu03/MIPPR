# MIPPR

Microplastic Image Processing Pipeline for Research.

Manual classification of microplastics larger than 500 µm (color, morphology, size) is slow, hard to standardize, and depends on who is looking. MIPPR measures and classifies hand-picked particles from photos the same way every time. It is a free, open-source web app, with a Python pipeline for the lab.

**Every photo is taken on one of three printed backgrounds** ([backgrounds/](backgrounds/README.md)): a white grid, a black grid or a checkerboard, one particle per box. Their corner markers give the scale, the flattening and the background type, so photos without a printed sheet are not accepted.

## The 10 parts

The repo is organized by the project's 10 parts. Each has its own folder, README (what it takes in and produces, what exists, what is left to build) and GitHub issue, so it can be worked on separately.

| # | Part | Method | Folder | Status |
|---|---|---|---|---|
| 1 | Capture and calibration | printed design + geometry | [pipeline/mippr/capture/](pipeline/mippr/capture/README.md), [backgrounds/](backgrounds/README.md) | working on synthetic photos, with a photo quality check; real photos next |
| 2 | Segmentation | threshold | [pipeline/mippr/segmentation/](pipeline/mippr/segmentation/README.md) | working on synthetic sheet photos; real sheet photos next |
| 3 | Measurement | geometry | [pipeline/mippr/measurement/](pipeline/mippr/measurement/README.md) | working; the lab's numbers are 8–12% smaller on some photos, within 2% on others |
| 4 | Colour | rules | [pipeline/mippr/color/](pipeline/mippr/color/README.md) | provisional rules; 96% agreement on white backgrounds, weak on black; need white-balanced photos to fit |
| 5 | Morphology | rules + image model | [pipeline/mippr/morphology/](pipeline/mippr/morphology/README.md) | rules working; model planned |
| 6 | Review and correction | people | [pipeline/mippr/review/](pipeline/mippr/review/README.md), `web/src/review/` | correction rules working; screen planned |
| 7 | Ground truth and validation | labelled data | [validation/](validation/README.md) | measurement code checked on 20 of the lab's older photos ([report](validation/reports/lab_photos.md)); labelled sheet photos next |
| 8 | App, batch and outputs | software | [web/](web/README.md), `pipeline/mippr/export.py`, `cli.py` | exports working; browser app started (sheet and markers, parity-tested); tests run on every push |
| 9 | Storage | Supabase | [database/](database/README.md) | draft schema |
| 10 | Model retraining and versioning | process | [training/](training/README.md) | planned |

Parts 1–6 flow in order for every photo: capture → segment → measure → colour → morphology → review. Part 7 tunes and judges parts 2–5. Parts 8–10 deliver and maintain the result.

## Plan and decisions

- [Plan and checklist](docs/PIPELINE.md): every task, grouped by part, with inputs, outputs and risks ([interactive tracker](docs/pipeline-tracker.html))
- [Project context](CLAUDE.md): copy of the team's Google Drive CLAUDE.md, the source for conceptual decisions (spec v0.6)
- [Classification spec](docs/CLASSIFICATION_SPEC.md): what is measured and decided for every particle, and how each value is obtained
- [Output CSV](docs/OUTPUT_CSV.md): every exported column
- [Technical decisions](docs/TECHNICAL_DECISIONS.md): technical choices and findings, made after Drive
- [The lab's existing particle records](docs/LAB_DATA.md): the hand-classification spreadsheets and photos in Drive, and how the app compares

## Try it

```bash
python -m venv .venv && .venv/bin/pip install -r pipeline/requirements.txt
cd pipeline && ../.venv/bin/python -m pytest tests
```

See [pipeline/README.md](pipeline/README.md) for printing a background and measuring a photo.
