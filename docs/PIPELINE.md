# MIPPR plan: the 10 parts

Every action needed for MIPPR to work, grouped into the project's 10 parts. Each part has its own folder and README in the repo, so it can be worked on separately. Check items off as they are finished (edit this file or use the linked issues).

Conceptual decisions and project context live in [CLAUDE.md](../CLAUDE.md) (Drive spec v0.6). What the pipeline measures and outputs is in [CLASSIFICATION_SPEC.md](CLASSIFICATION_SPEC.md) and [OUTPUT_CSV.md](OUTPUT_CSV.md), and technical decisions are in [TECHNICAL_DECISIONS.md](TECHNICAL_DECISIONS.md). The working code is the Python reference pipeline in [pipeline/](../pipeline/README.md).

*Reorganized into 10 parts on November 12, 2026 (it was 11 stages).* After editing this file, run `python scripts/sync_plan.py` to refresh [pipeline-tracker.html](pipeline-tracker.html); `--issues DIR` also writes matching text for the GitHub issues.

| Part | Folder | Method |
|---|---|---|
| 1. Capture and calibration | [pipeline/mippr/capture/](../pipeline/mippr/capture/README.md), `backgrounds/` | printed design + geometry |
| 2. Segmentation | `pipeline/mippr/segmentation/` | threshold |
| 3. Measurement | `pipeline/mippr/measurement/` | geometry |
| 4. Colour | `pipeline/mippr/color/` | rules |
| 5. Morphology | `pipeline/mippr/morphology/`, `training/` | rules + image model |
| 6. Review and correction | `pipeline/mippr/review/`, `web/src/review/` | people |
| 7. Ground truth and validation | `validation/` | labelled data, comparison |
| 8. App, batch and outputs | `web/`, `pipeline/mippr/export.py`, `cli.py`, `batch.py` | software |
| 9. Storage | `database/`, `web/src/storage/` | Supabase |
| 10. Model retraining and versioning | `training/` | process |

## 1. Capture and calibration

**Goal:** Turn a photo into a flat, correctly scaled, colour-corrected image whose grid geometry is known exactly.

**Flow:** Photo of particles on a printed sheet -> Flattened grid image + scale + white balance

Folder: [pipeline/mippr/capture/](../pipeline/mippr/capture/README.md) and `backgrounds/`. Every number downstream depends on this part.

- [ ] Pick the imaging setup and lock height, zoom and lighting. Proposed: diffuse even light, no flash, roughly overhead, phone-friendly.
- [ ] Set a minimum photo resolution. The lab's ruler photos are 33–63 µm/px; the old checkerboard photos about 75 µm/px, where a 500 µm particle is only about 7 px across. Fiber widths (about 24 µm) can't be resolved on a whole-sheet photo.
- [x] Choose the backgrounds. Decided in Drive v0.6: three grids with identical square boxes (white boxes/black lines, black boxes/white lines, checkerboard), one particle per box; the box label is the particle ID.
- [x] Make the printable sheets: `backgrounds/` (vector PDF, Letter and A4; corner markers encoding the background, 100 mm line, white/grey patches, row and column labels)
- [x] Choose the sheet design: "Standard" for all three backgrounds (12 mm boxes, 0.5 mm lines, each box's label printed in its corner), chosen November 5 from three options
- [ ] Test the Standard design with the largest particles and long fibers on real photos (open question 1a)
- [ ] Test the checkerboard against the two lined grids on real photos, especially particles across a black/white edge (open question 1)
- [ ] Choose paper (matte paper or cardstock), and check whether printer black varies enough between printers to matter (open question 1b)
- [x] Put a scale reference in every frame: corner markers at a known printed size, plus a printed 100 mm line to check printer scaling.
  - Four corner markers alone can't correct lens distortion. The grid's own line crossings do: about 0.1 px in synthetic tests.
- [ ] Put a color reference in every frame. The white and grey patches are on the sheets; decide whether hue classes also need colored patches.
- [x] Keep the grid in the center, clear of the markers, with row/column labels and the patches in the margin
- [x] Correct perspective and lens distortion on the printed grids: markers first, then the grid's line crossings (or checkerboard corners). About 0.1 px in synthetic tests; not yet tested on real photos.
- [x] Correct perspective and lens distortion on the lab's legacy checkerboard: each square is warped using its own four corners (about 3 px down to 0.1 px)
- [x] Read the scale from the corner markers, with the 100 mm check line correction (`--line-mm`, sets `flag_scale`)
- [x] Read the scale from the legacy checkerboard: µm/px = square size / px per square
- [x] Normalize white balance using the printed white patch; the grey patch is checked (`run.json`)
- [x] Write unit tests on synthetic photos with tilt, lens distortion, uneven light, blur and noise
- [x] Check photo quality before processing and give a clear message instead of a bad result (`capture/calibration.py` `check_quality`): missing markers, blur, too dark, overexposed, glare, uneven light, colour cast, too few px per mm. Limits set on degraded synthetic photos; `run.json` records them.
- [ ] Confirm the quality limits on the first real phone photos of the printed sheets (blur 0.30 mm, white patch 110, 10 px/mm)
- [x] Scale fallback for photos without the printed sheet: read a ruler's ticks with no help (`validation/ruler.py`: finds the millimetre edge, tells it from an inch edge, refines over hundreds of ticks; right on 21 of the lab's 22 ruler photos, checked by eye)
- [ ] Port the ruler reader to the browser for photos without the sheet; inch-only rulers aren't read
- [ ] Record pixels per mm for each setup and check it against a ruler image
- [ ] Measure a printed legacy checkerboard square with a ruler. The notes say 10 mm; the ImageJ results imply 10.07 mm.
- [ ] Set file naming and folder layout. The metadata fields are already decided in the spec: sample ID, date, operator, lab, setup, site.

**In:** A photo on a printed sheet (or the lab's legacy checkerboard).  
**Out:** Flattened grid image, layout, px per mm, white balance, scale flags.  
**Watch for:** Glare, shadows and scale errors. Fixing them at capture is cheaper than in code, and a scale error moves every particle.

## 2. Segmentation

**Goal:** Find each particle in its box and draw its outline.

**Flow:** Flattened grid image -> One outline per particle + its box

Folder: [pipeline/mippr/segmentation/](../pipeline/mippr/segmentation/README.md). Errors here carry into every measurement and label.

- [x] Build a classical baseline: difference from the known background, hysteresis threshold, half-maximum edge placement
- [x] Segment box by box on the three printed grids, each box against its own background colour, with no template photo (synthetic tests)
- [x] Legacy board: difference from an empty-board photo, brightness-matched square by square
- [x] Handle printed lines: the difference is bridged across lines and label corners, so a line never becomes a particle
- [x] Keep fibers that cross a printed line in one piece (`flag_line`)
- [x] Handle touching particles: avoided by design (one particle per box). Two blobs in a box are kept as separate rows with `flag_multi_blob`.
- [x] Remove debris and edge artifacts with a minimum area and the sliver rule; particles at the grid's edge are kept with `flag_edge`
- [x] Write out an overlay image of outlines on the photo for every input
- [ ] Handle translucent films and clear particles. Low-contrast outlines are flagged for review for now.
- [ ] Detect thin fibers (about 24 µm wide, under one pixel on a sheet photo) as faint lines, so their length can be measured
- [ ] Test grid segmentation on real phone photos of the printed sheets
- [ ] Score segmentation on the labelled set: detection recall and precision, outline overlap. On the lab's two ruler photos every particle was found.
- [ ] Optional: compare with a learned segmenter (Cellpose, SAM or a small U-Net), only if the threshold falls short

**In:** Flattened grid image and layout from part 1.  
**Out:** Labels, difference map, line band, box per particle.  
**Watch for:** Fibers and clear particles are the usual failures. Look at failures by class, not only the average.

## 3. Measurement

**Goal:** Turn each outline into size and shape numbers in mm, the same every time.

**Flow:** Outlines + scale -> Size, shape, fiber length and opacity per particle

Folder: [pipeline/mippr/measurement/](../pipeline/mippr/measurement/README.md).

- [x] Fix the size cutoff and which dimension it applies to. Decided: longest length (max Feret) is the main size. A particle is flagged if its min width is under 500 µm or its longest length is 450–550 µm.
- [x] Compute area, CED, max and min Feret, aspect ratio, perimeter, convex area/perimeter, bounding box, circularity and solidity (ImageJ conventions)
- [x] Compare perimeter methods on shapes with a known answer. The sub-pixel outline is most accurate; ImageJ-compatible values are kept alongside (provisional).
- [x] Measure fiber length along the centre line (`fiber_length_mm`): skeleton path smoothed, ends trimmed and added back; within about 1–3% on test shapes; used only for particles that bend
- [x] Measure opacity against the known background of each box (`opacity`): a lower bound on one background, measured directly across a checkerboard edge
- [x] Convert pixels to mm and mm² with the stored scale; flag particles near the 500 µm cutoff or narrower than it
- [x] Leave width empty with `flag_width_unresolved` when a particle is under about 2 px wide
- [ ] Later decision: which perimeter method gives the headline circularity (sub-pixel or ImageJ-compatible; spec section 5)
- [ ] Check opacity on real photos of clear films, against the opposite background

**In:** Labels, difference map, image and scale from parts 1–2.  
**Out:** One row per particle with the size and shape columns of OUTPUT_CSV.md.  
**Watch for:** A scale error shifts every particle across the 500 µm line, so check calibration before trusting counts.

## 4. Colour

**Goal:** Give each particle one of the 13 colour classes, plus its second colour and that colour's share.

**Flow:** White-balanced image + outline -> Colour label, confidence, second colour

Folder: [pipeline/mippr/color/](../pipeline/mippr/color/README.md).

- [x] List color classes: 13 classes. Clear and white are kept separate by opacity; multicolor means a second, clearly different color covers ≥ 20%.
- [x] Measure mean and SD of CIE Lab per particle, ignoring edge pixels, plus a hex code
- [x] Classify every pixel into a colour class (provisional Lab rules) and record the main colour, the second colour and its share (`color_secondary`, `color_secondary_fraction`)
- [ ] Fit the colour rules to labelled particles. Tried on the lab's photos (`validation/fit_colors.py`): no gain (90.9% vs 90.8%), because the photos aren't white-balanced (a purple-blue cast on every particle) and almost all particles are black. Needs white-balanced photos of the printed sheets with coloured particles; the rules stay `0.1-provisional`.
- [ ] Add a reference swatch and Lab range per color class to the spec (once the color reference is settled in part 1)
- [ ] Check clear vs white on real photos on both backgrounds

**In:** White-balanced image, outline and opacity.  
**Out:** `color_label`, `color_confidence`, `color_secondary`, `color_secondary_fraction`.  
**Watch for:** A wrong white balance moves particles across color classes. Fix it in part 1.

## 5. Morphology

**Goal:** Give each particle a shape class: rules where measurements decide, an image model where they can't.

**Flow:** Shape values + particle crop -> Morphology label, source, confidence

Folder: [pipeline/mippr/morphology/](../pipeline/mippr/morphology/README.md) (rules, model interface) and [training/](../training/README.md) (training code).

- [x] List morphology classes with a written visual rule for each: fragment, rubbery fragment, fiber, film, foam, pellet, other. A fiber is length:width ≥ 3:1. Rubbery fragment was added on November 11 from the lab's records.
- [x] Classify fiber, pellet and film by rules (v2): length:width ≥ 3 (centre-line ratio for particles that bend), round and solid for pellet, low opacity for film. The thresholds are provisional.
- [ ] Tune the rule thresholds on the lab's labels. The lab records some ≥ 3:1 particles as fragments, so the fiber rule may need a thinness condition.
- [ ] Cut particle crops with the background blanked (`crop_particle`), for training and inference
- [ ] Train an image model on crops + shape values (v3) for fragment, rubbery fragment and foam. Compare a classifier chain with one multi-task model.
- [ ] Decide when the model may overrule a rule (decided that it may; set the confidence from validation data)
- [ ] Add 2–3 example photos per morphology class to the spec

**In:** Shape values, opacity and crops from parts 2–4; the labelled set from part 7.  
**Out:** `morphology_label`, `morphology_source`, confidence and runner-up.  
**Watch for:** The model can't beat the agreement between two people labelling the same particles. Measure that number first.

## 6. Review and correction

**Goal:** Let a person reject false detections and fix outlines and labels before export, and keep what they did.

**Flow:** Particle rows + overlay -> Reviewed rows + new labels

Folder: [pipeline/mippr/review/](../pipeline/mippr/review/README.md) (rules for applying decisions) and `web/src/review/` (the screen).

- [x] Decide how 'not plastic' particles are handled and what the output says when the model is unsure. The app doesn't test plastic or polymer, and every export says so. Uncertain particles get `review_reason` flags. `polymer_confirmed` columns are left for the lab.
- [x] Decide the review columns: `review_status`, `*_original` labels, `outline_edited`, reviewer, role and time; rejected rows stay in particles.csv and leave the summary
- [x] Apply reviewer decisions (`review/corrections.py`): confirm, reject, relabel, edit outline (re-measured exactly as the pipeline would), tag; original labels kept
- [ ] Split and merge: decide the new particle IDs and what happens to the merged-away row
- [x] Order the review list: flagged and low-confidence particles first, then unflagged, reviewed, rejected (`review_queue`)
- [ ] Set the `flag_low_confidence` threshold from validation data
- [ ] Build the review screen: outlines on the photo, accept / reject / relabel / redraw, keyboard shortcuts, tar-like and bundle tags
- [ ] Count how many particles need review and how long it takes

**In:** Rows and overlays from parts 2–5.  
**Out:** Reviewed rows, and labels for parts 7 and 10.  
**Watch for:** Reviewers correct labels and outlines, never numbers, so every measurement still traces back to an outline.

## 7. Ground truth and validation

**Goal:** Build the known answers that tune and judge every other part, and show with numbers that the app can be trusted.

**Flow:** Lab records + new labels + app output -> Labelled set, gold set, validation report

Folder: [validation/](../validation/README.md). The lab's data stays in Drive.

- [x] Find out whether a labeled set already exists from past hand-classification (open question 4). It does: about 4,600 particles with shape and colour, and about 4,000 with hand-measured length and width, in the Drive ParticleCount spreadsheets ([LAB_DATA.md](LAB_DATA.md)).
- [x] Match the lab's "Rows A–H" photos to their spreadsheet rows by sample and well (`validation/lab_photo_check.py`; 20 photos so far)
- [x] Compare automated sizes with the lab's ImageJ results on the fragment_area sample. Median differences across 24 particles: area +0.5%, Feret −0.2%, min Feret +0.1%.
- [ ] Settle the scale gap with the lab: the app's sizes are 8–12% larger than the sheet on five EX_01 photos but within 2% on three others. Measure one particle from EX_01_S07 with calipers.
- [ ] Ask the lab how length and width are measured, and why width is larger than length in SF_02/SF_03
- [x] Run the photo check on more samples and collect the matches into one table: 20 photos, 1,210 particles paired, 8 photos reliable ([report](../validation/reports/lab_photos.md)). The size gap varies by photo (+12% to −2%), so it comes from the lab's scale settings, not the app. SF_04 has no sheet in Drive.
- [ ] Compare automated sizes with manual caliper or microscope measurements on 50 particles
- [ ] Shoot a pilot batch of 50 to 100 particles on the printed sheets, covering every class
- [ ] Choose an annotation tool (CVAT, Label Studio or similar) and set it up with the class list from the spec
- [ ] Outline particles and tag color and morphology on at least 300 particles, including film, foam and clear particles
- [ ] Have a second person label a 20% subset independently
- [ ] Measure agreement between labelers (Cohen's kappa for classes, overlap for outlines)
- [ ] Resolve disagreements and update the class spec from what you learn
- [ ] Split into train, validation and test sets by sample, not by image
- [ ] Agree how close to hand measurements counts as validated (open question 6), after seeing the agreement per class
- [ ] Run the pipeline once on the held-out test set and do not tune on it
- [ ] Report detection recall and precision, class confusion matrices, and size error in mm
- [ ] Compare model-versus-human agreement with human-versus-human agreement
- [ ] Time the manual workflow against the pipeline on the same batch
- [ ] Run a small test on images from a second setup or lab

**In:** The lab's spreadsheets and photos, new labels from review, the app's output.  
**Out:** Tuned thresholds, a split labelled set, a gold test set, and a validation report.  
**Watch for:** Don't tune on the test set. A method proven only on the pilot setup isn't a standard method.

## Decision point: build the web app?

Go only if validation met its targets, the batch tool runs for someone other than you, and there is a hosting and maintenance plan. Otherwise release the command-line tool and documentation as the finished project.

The stack is already decided (CLAUDE.md, v0.6): a static site on Cloudflare Pages with OpenCV.js and ONNX Runtime Web in the browser, and Supabase (database, storage and reviewer sign-in) as the only backend. Image processing stays in the browser. The release plan builds the app in stages (v1 measurement, v2 color rules, v3 morphology model, v4 label contributions), so this decision applies to each release.

- [ ] Validation targets met
- [ ] A second person ran the batch tool without help
- [ ] Hosting and upkeep plan agreed (who maintains it after the practicum: open question 7)

## 8. App, batch and outputs

**Goal:** Let researchers and community scientists use the pipeline: a batch tool for the lab and a browser app for everyone, with tidy outputs.

**Flow:** Photos + sample details -> CSV, overlays, summary (in the browser or from a folder)

Folder: [web/](../web/README.md) (browser app; `src/` mirrors the pipeline parts) and `pipeline/mippr/export.py`, `cli.py`, `batch.py`.

- [x] Choose the output table columns and units before any code exists. Now mm and mm², merged with the team's data dictionary draft: [OUTPUT_CSV.md](OUTPUT_CSV.md).
- [x] Write a per-particle CSV and QC overlays (columns as in OUTPUT_CSV.md, plus `NOTE.txt`)
- [x] Write per-sample summary counts (`summary.csv`: counts by morphology, color and size class, length distribution, review and flag counts)
- [x] Log versions, settings and scale used for every run so results can be reproduced (`run.json`)
- [x] Write a README with install steps and a worked example ([pipeline/README.md](../pipeline/README.md))
- [ ] Process a whole folder with one command and one settings file (`batch.py`, planned); report each failed photo and why
- [ ] Time it on 500 images and fix the slowest step
- [ ] Sketch the screens: print background, upload, sample details, run, review, export
- [x] Offer the printable backgrounds on the website (download table in `web/index.html`)
- [ ] Port parts 1–5 to the browser module by module (`web/src/`), each passing parity tests against the Python pipeline
  - Done: the official OpenCV.js 4.10.0 build has ArUco (`cv.aruco_ArucoDetector`); its marker corners match Python's to 0 px.
  - Done: sheet layout, marker detection and rectification (`web/src/capture/sheet.js`), parity-tested against Python.
  - Next: grid-crossing refinement (`rectify_grid`); the checkerboard needs a JS `cornerSubPix`, which 4.10.0 lacks.
  - Write a marching-squares step for the sub-pixel perimeter and a skeleton step for fiber length, which OpenCV.js lacks.
- [ ] Run batches in the browser on the user's machine (no processing server)
- [ ] Build the upload and progress screens, and a results table with overlays
- [ ] Support scale entry for photos without the printed sheet, with clear guidance on how to take the photo
- [ ] Export CSV and the overlay image, plus a PDF or HTML summary
- [ ] Host on Cloudflare Pages from the GitHub repo, with upload size limits
- [x] Run the tests on every push (GitHub Actions: pipeline, ruler reader, browser parity tests, plan in sync)
- [ ] Choose a license and add contribution notes
- [ ] Write the methods page: class definitions, calibration, accuracy and known limits
- [ ] Tag version 1.0 with a changelog
- [ ] Pilot with two or three outside users and collect what confused them
- [ ] Draft a short paper or report and share the repository with the lab group

**In:** The pipeline (parts 1–6), validation results.  
**Out:** A batch tool, a hosted app and a public repository.  
**Watch for:** Community photos will vary far more than lab photos. Plan for quality checks on upload and for retraining with corrected labels.

## 9. Storage

**Goal:** Keep results, labels and model versions in one place, safely and for free.

**Flow:** Rows + review decisions -> Supabase tables + snapshots

Folder: [database/](../database/README.md) (draft schema) and `web/src/storage/` (client).

- [ ] Decide what is stored: full photos, crops only, or only measurement rows (Drive open question 9b)
- [ ] Set up Supabase: tables for samples, images, particles, labels and model versions, with Row Level Security on every table and no service-role key in client code. A draft is in `database/migrations/0001_draft_schema.sql`.
- [ ] Add reviewer sign-in with Supabase Auth (expert or community role)
- [ ] Save confirmed and corrected labels to Supabase from the review screen
- [ ] Export a versioned database snapshot for each retraining and for publishing
- [ ] Check Supabase free-tier limits and how to keep the project from pausing (open question 9c); set a data retention policy
- [ ] Agree the data license and consent terms for contributed photos and labels (open question 9)
- [ ] Publish the labeled dataset or a sample, with a data card (e.g. on Zenodo for a citable DOI per version)

**In:** Rows from part 8, decisions from part 6.  
**Out:** A shared record of every sample, and snapshots for parts 7 and 10.  
**Watch for:** Free-tier limits and pausing. Keep exported snapshots as backups.

## 10. Model retraining and versioning

**Goal:** Keep the morphology model improving from corrected labels without letting it drift.

**Flow:** Snapshot of reviewed labels -> Candidate model -> Gate on the gold set -> New version

Folder: [training/](../training/README.md). Periodic and manual, not continuous online learning.

- [ ] Build a fixed, expert-labelled gold test set that is never used for training
- [ ] Set up the retraining routine: snapshot, build the dataset, train, evaluate, gate, publish (`training/` stubs)
- [ ] Version every model and record its gold-set scores (`model_versions`), so past results stay reproducible
- [ ] Decide where training runs: a lab GPU machine or free notebooks (open question 8)
- [ ] Set a plan for who answers issues and retrains the model after the practicum (open question 7)
- [ ] Publish models (GitHub releases, Hugging Face or Zenodo)

**In:** Labelled set (part 7), snapshots (part 9).  
**Out:** Approved model versions for part 5.  
**Watch for:** Community labels vary more than expert labels. Weight them, and keep them out of the gold set.
