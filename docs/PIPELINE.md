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

**Goal:** Turn a photo on one of the three printed backgrounds into a flat, correctly scaled, colour-corrected image whose grid geometry is known exactly. Every photo is taken on a printed sheet; there is no other input.

**Flow:** Photo of particles on a printed sheet -> Flattened grid image + scale + white balance

Folder: [pipeline/mippr/capture/](../pipeline/mippr/capture/README.md) and `backgrounds/`. Every number downstream depends on this part.

- [ ] Pick the imaging setup and lock height, zoom and lighting. Proposed: diffuse even light, no flash, roughly overhead, phone-friendly.
- [ ] Set a minimum photo resolution for a whole-sheet phone photo (the quality check rejects under 10 px/mm, where a 500 µm particle is 5 px across). Fiber widths (about 24 µm) can't be resolved on a whole-sheet photo.
- [x] Choose the backgrounds. Decided in Drive v0.6: three grids with identical square boxes (white boxes/black lines, black boxes/white lines, checkerboard), one particle per box; the box label is the particle ID.
- [x] Make the printable sheets: `backgrounds/` (vector PDF, Letter and A4; corner markers encoding the background, 100 mm line, white/grey patches, row and column labels)
- [x] Choose the sheet design: "Standard" for all three backgrounds (12 mm boxes, 0.5 mm lines, each box's label printed in its corner), chosen November 5 from three options
- [ ] Test the Standard design with the largest particles and long fibers on real photos (open question 1a)
- [ ] Test the checkerboard against the two lined grids on real photos, especially particles across a black/white edge (open question 1)
- [x] Choose paper: matte paper (decided November 18, 2026)
- [x] Make the printer not matter (user, November 18). Printer black, grey and colours change no result: segmentation measures each box's own colour in the photo, white balance uses the paper white, and the grey and coloured patches are only a check and a record. Printer scaling ("fit to page") is measured from the paper's four edges when they are in the photo, through a lens model fitted to the crossings and markers, and corrected above 1% (`scale_source = paper_edges`); within 0.1% on synthetic prints at 94–100%, including A4 fitted onto Letter. Python and browser.
- [ ] Check the paper-edge scale on real phone photos (paper on a darker surface), and how often all four edges are in frame
- [x] Put a scale reference in every frame: corner markers at a known printed size, plus a printed 100 mm line to check printer scaling.
  - Four corner markers alone can't correct lens distortion. The grid's own line crossings do: about 0.1 px in synthetic tests.
- [x] Put a color reference in every frame: white and grey patches on every sheet, plus a version of each sheet with six coloured patches (`backgrounds/*_color.pdf`, own marker IDs 24–47; their colours after white balance go in `run.json`). Printers render colours differently, so they are a record, not a standard (user, November 18).
- [x] Keep the grid in the center, clear of the markers, with row/column labels and the patches in the margin
- [x] Correct perspective and lens distortion on the printed grids: markers first, then the grid's line crossings (or checkerboard corners). About 0.1 px in synthetic tests; not yet tested on real photos.
- [x] Read the scale from the corner markers, with the 100 mm check line correction (`--line-mm`, sets `flag_scale`)
- [x] Normalize white balance using the printed white patch; the grey patch is checked (`run.json`)
- [x] Write unit tests on synthetic photos with tilt, lens distortion, uneven light, blur and noise
- [x] Check photo quality before processing and give a clear message instead of a bad result (`capture/calibration.py` `check_quality`): missing markers, blur, too dark, overexposed, glare, uneven light, colour cast, too few px per mm. Limits set on degraded synthetic photos; `run.json` records them. A photo without the sheet's markers is refused with a message saying to photograph it on a printed background.
- [ ] Confirm the quality limits on the first real phone photos of the printed sheets (blur 0.30 mm, white patch 110, 10 px/mm)
- [ ] Check the marker scale against a ruler on the first real sheet photos (it should agree to well under 1%)
- [ ] Set file naming and folder layout. The metadata fields are already decided in the spec: sample ID, date, operator, lab, setup, site.

**In:** A photo on a printed sheet: white grid, black grid or checkerboard.  
**Out:** Flattened grid image, layout, px per mm, white balance, scale flags.  
**Watch for:** Glare, shadows and scale errors. Fixing them at capture is cheaper than in code, and a scale error moves every particle.

## 2. Segmentation

**Goal:** Find each particle in its box and draw its outline.

**Flow:** Flattened grid image -> One outline per particle + its box

Folder: [pipeline/mippr/segmentation/](../pipeline/mippr/segmentation/README.md). Errors here carry into every measurement and label.

- [x] Build a classical baseline: difference from the known background, hysteresis threshold, half-maximum edge placement
- [x] Segment box by box on the three printed grids, each box against its own background colour, with no template photo (synthetic tests)
- [x] Handle printed lines: the difference is bridged across lines and label corners, so a line never becomes a particle
- [x] Keep fibers that cross a printed line in one piece (`flag_line`)
- [x] Handle touching particles: avoided by design (one particle per box). Two blobs in a box are kept as separate rows with `flag_multi_blob`.
- [x] Remove debris and edge artifacts with a minimum area and the sliver rule; particles at the grid's edge are kept with `flag_edge`
- [x] Write out an overlay image of outlines on the photo for every input
- [ ] Handle translucent films and clear particles. Low-contrast outlines are flagged for review for now.
- [ ] Detect thin fibers (about 24 µm wide, under one pixel on a sheet photo) as faint lines, so their length can be measured
- [ ] Test grid segmentation on real phone photos of the printed sheets
- [ ] Check segmentation on labelled photos of the printed sheets: detection counted from the well-to-box list, and outlines looked at where a particle's size or shape came out wrong (part 7). No hand-drawn outlines. (On the lab's older ruler photos, used only as a check, 650 particles paired reliably.)
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
- [x] Compare perimeter methods on shapes with a known answer. The sub-pixel outline is most accurate; since November 18 ImageJ's values are the main columns and the sub-pixel ones are kept alongside.
- [x] Measure fiber length along the centre line (`fiber_length_mm`): skeleton path smoothed, ends trimmed and added back; within about 1–3% on test shapes; used only for particles that bend
- [x] Measure opacity against the known background of each box (`opacity`): a lower bound on one background, measured directly across a checkerboard edge
- [x] Convert pixels to mm and mm² with the stored scale; flag particles near the 500 µm cutoff or narrower than it
- [x] Leave width empty with `flag_width_unresolved` when a particle is under about 2 px wide
- [x] Measure how much each size depends on where the edge is drawn (`measurement/uncertainty.py`): length and width with the edge at 40% and 60% of the particle's contrast, `size_uncertainty`, and `flag_size_uncertain` above a provisional 0.10
- [ ] Set the `flag_size_uncertain` threshold in testing (part 7), separately for fibers if their fading ends need it
- [x] Decided (user, November 18, 2026): **ImageJ is the main guideline for every measurement**, with other useful methods kept as extra columns. Length stays ImageJ's Feret over pixel corners; perimeter, circularity and aspect ratio (fitted ellipse) are now ImageJ's, plus roundness and major/minor axes; the sub-pixel perimeter and circularity and the Feret length:width are kept alongside. On the fragment_area sample: AR −0.1%, Round +0.2%, Circ. +3.0% against ImageJ's own results.
- [x] ~~Decide how max Feret is measured~~ (ImageJ's, above): over pixel corners (ImageJ's convention, now) it reads about 1.25 px long even on a perfect disc; at a whole-sheet photo's 10 px/mm that is +0.12 mm, about 6% on a 2 mm particle and 25% near the 0.5 mm cutoff. Option: a sub-pixel Feret from the outline as the headline, with the ImageJ value kept alongside (as for perimeter). On synthetic shapes the sub-pixel length is more consistent (spread 0.58 vs 0.99 px) but reads slightly short; decide on the labelled sheet photos with calipers.
- [x] Which perimeter method gives the headline circularity: ImageJ's (above)
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
- [ ] Fit the colour rules to labelled particles photographed on the sheets (white-balanced by the grey patch). Tried on the lab's older photos (`validation/fit_colors.py`): no gain (90.9% vs 90.8%), because the photos aren't white-balanced (a purple-blue cast on every particle) and almost all particles are black. Needs white-balanced photos of the printed sheets with coloured particles; the rules stay `0.1-provisional`.
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
- [ ] Tune the rule thresholds on labelled particles photographed on the sheets. Pellet: fixed November 18. Small round particles measured ImageJ solidity 0.87–0.94 at 10 px/mm, under the 0.95 starting value, so the rule now uses the sub-pixel solidity (`solidity_subpixel`, 0.998–1.0 on round particles of any size; 0.58–0.89 on star, L and bitten shapes).
- [ ] Fibers: on hold (advisor, November 18). The advisor will send fiber photos; the lab usually removes fibers by other methods. Whether a fiber is a thin thread or anything ≥ 3:1, and whether the Gyre sheet's "Line" / "Line Bundle" are fiber / fiber bundle, wait until then.
- [ ] Rubbery fragment (advisor, November 18): wanted as its own class if the model can tell it apart; if not, the app says fragment and the reviewer marks whether it is rubbery. Decided by how it performs (v3).
- [ ] Tar-like: reviewer tag or class? Not decided yet (a tag for now)
- [x] Cut particle crops with the background blanked (`pipeline/mippr/crops.py`, `web/src/crops.js`): full resolution, square, padded, background transparent; saved as `crops/<particle_ref>.png` and named in `crop_file`, with the photo in `photo_file`. `morphology/model.py` `model_input` puts a crop on grey at the model's size.
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
- [x] Split and merge (November 18): split pieces of B4 become B4-1, B4-2 (the next free numbers in the box); a merge takes B4 if free, else the next free number; the rows replaced stay in particles.csv, marked rejected, and each new row names them in `derived_from`. `review/corrections.py` / `corrections.js` (`split`, `merge`, through `apply_all`), parity-tested; on the review screen: Split (drag a cut line), Merge with… (click the other particle; the merged outline is the hull of both, redraw it if needed).
- [x] Order the review list: flagged and low-confidence particles first, then unflagged, reviewed, rejected (`review_queue`). Flagged includes `flag_size_uncertain`, so sizes the app isn't sure of are checked first.
- [ ] Set the `flag_low_confidence` threshold from validation data
- [x] Build the review screen (`web/src/review/screen.js`): outlines on the photo coloured by status, click or keyboard to select, confirm / reject / relabel, tar-like and bundle tags, review order; the rules are `review/corrections.js`, the port of corrections.py (parity-tested)
- [x] Redraw an outline on the review screen (draw round the particle; re-measured with `edit_outline`)
- [ ] Count how many particles need review and how long it takes

**In:** Rows and overlays from parts 2–5.  
**Out:** Reviewed rows, and labels for parts 7 and 10.  
**Watch for:** Reviewers correct labels and outlines, never numbers, so every measurement still traces back to an outline.

## 7. Ground truth and validation

**Goal:** Build the known answers that tune and judge every other part, and show with numbers that the app can be trusted.

**Flow:** Lab records + new labels + app output -> Labelled set, gold set, validation report

Folder: [validation/](../validation/README.md). The lab's data stays in Drive.

The app only takes photos on the three printed backgrounds, so the labelled set, the gold set and the pass marks are built from photos on the sheets. The lab's older photos (a ruler on white or black paper, and the old 12 × 24 checkerboard) are only a cross-check of the measurement code. The quickest route to a labelled set on the sheets: re-photograph the lab's already-labelled particles, one per box, recording which well went into which box, so the hand labels carry over.

**What the labelled particles test** (decided November 12): whether the app gets each particle's **size, colour and morphology** right, compared box by box with the lab's answer. Finding particles in the photo is mostly solved by the one-per-box design, so it isn't labelled separately: no hand-drawn outlines. An outline is looked at only when that particle's size or shape comes out wrong, to see why.

**Testing, then use.** In testing, the known answers show which flags go with wrong results, and that sets each flag's threshold (for example, above what `size_uncertainty` sizes turn out wrong). In use there are no known answers: the same checks run on every particle with those thresholds, and flagged particles go to a reviewer first. Reviewer corrections are later used to check the thresholds again (part 10).

- [x] Find out whether a labeled set already exists from past hand-classification (open question 4). It does: about 4,600 particles with shape and colour, and about 4,000 with hand-measured length and width, in the Drive ParticleCount spreadsheets ([LAB_DATA.md](LAB_DATA.md)).
- [x] Match the lab's "Rows A–H" photos to their spreadsheet rows by sample and well (`validation/lab_photo_check.py`; 20 photos so far)
- [x] Compare automated sizes with the lab's ImageJ results on the fragment_area sample. Median differences across 24 particles: area +0.5%, Feret −0.2%, min Feret +0.1%.
- [x] ~~Settle the scale gap with the lab~~: left as is (user, November 18). The new sheet photos replace the older photos for validation.
- [ ] Ask the lab how length and width are measured, and why width is larger than length in SF_02/SF_03
- [x] Run the photo check on more samples and collect the matches into one table: 20 photos, 1,210 particles paired, 8 photos reliable ([report](../validation/reports/lab_photos.md)). The size gap varies by photo (+12% to −2%), so it comes from the lab's scale settings, not the app. SF_04 has no sheet in Drive.
- [x] Build the box-by-box check (`validation/sheet_check.py`), the lab's photo guide (`validation/PHOTO_PROTOCOL.md`) and the well-to-box, calipers and label templates; tested end to end on synthetic sheet photos
- [x] Permission: the lab's ParticleCount spreadsheets and photos may be used and published (advisor, November 18)
- [ ] Re-photograph the lab's labelled particles on the printed sheets (all three backgrounds), with a well-to-box list, so their hand labels and sizes carry over. The advisor will print the backgrounds, take the photos and make a CSV of each particle's morphology and colour (about two weeks from November 18).
- [ ] Compare box by box: length and width against the lab's sizes, colour and morphology against the lab's labels; report agreement per class and the confusion between classes
- [ ] Count detection from the well-to-box list: boxes with a particle the app missed, and extra detections in boxes listed empty
- [ ] Measure 30–50 of those particles with calipers (not yet agreed with the advisor), to decide which is right where the app and the lab's sizes disagree (the lab's older sizes vary by session)
- [ ] Set each flag's threshold from the results: `flag_size_uncertain` (which `size_uncertainty` goes with a wrong size), `flag_low_contrast`, `flag_merged`, and `flag_low_confidence` once confidences exist. Record how many wrong results each flag catches and how many it misses.
- [ ] Shoot a pilot batch of 50 to 100 particles on the printed sheets, covering every class
- [ ] Set up a per-box label sheet (sample, photo, box, colour, morphology, labeller), with the class lists from the spec; no outline annotation tool is needed
- [ ] Label colour and morphology (one label per box, no outlines) on at least 300 more particles on the sheets, including film, foam and clear particles
- [ ] Have a second person label a 20% subset independently
- [ ] Measure agreement between labelers (Cohen's kappa for classes)
- [ ] Resolve disagreements and update the class spec from what you learn
- [ ] Split into train, validation and test sets by sample, not by image
- [ ] Agree how close to hand measurements counts as validated (open question 6). Direction (November 18): the lab agrees the standard; sizes should be close, but applying the rules consistently matters more than always matching the hand measurement. The colour threshold and the multicolour / second-colour rules are set later.
- [ ] Run the pipeline once on the held-out test set and do not tune on it
- [ ] Report size error in mm, class confusion matrices for colour and morphology, detection counts, and what each flag catches
- [ ] Compare model-versus-human agreement with human-versus-human agreement
- [ ] Time the manual workflow against the pipeline on the same batch
- [ ] Run a small test on images from a second setup or lab

**In:** Labelled photos on the printed sheets (the lab's labelled particles re-photographed, and new labels from review), the app's output; the lab's spreadsheets and older photos as a cross-check.  
**Out:** Tuned thresholds, a split labelled set, a gold test set, and a validation report.  
**Watch for:** Don't tune on the test set. A method proven only on the pilot setup isn't a standard method.

## Decision point: build the web app?

**Deliverable (advisor, November 18):** the full web app, in about six months (around May 2027). The batch tool and documentation matter too, for papers afterwards.

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
- [x] Process a whole folder with one command and one settings file (`python -m mippr.cli batch`, `batch.py`): combined particles and per-sample summary, and a report of every photo processed or refused, with the reason and its quality problems
- [ ] Time it on 500 images and fix the slowest step
- [x] Build the screens: print a background, sample details and photos, measure with progress and a message per photo, check the results, download (`web/index.html`, `src/app.js`)
- [x] Offer the printable backgrounds on the website (download table in `web/index.html`)
- [x] Port parts 1–5 to the browser module by module (`web/src/`), each passing parity tests against the Python pipeline, and join them (`web/src/pipeline.js`)
  - Markers, crossings, flattening, white balance and the quality check; segmentation; measurement (with JS marching squares and skeleton); colour and shape rules; rows and CSV.
  - End to end on all three backgrounds: text, labels and flags identical to Python; numbers within about a pixel, because OpenCV.js 4.10's resampling differs from OpenCV 5's by up to one grey level (web/README.md).
- [x] Draw the overlay (outlines and box labels) on a canvas
- [x] Run batches in the browser on the user's machine (several photos per run, no processing server); a photo without a sheet is refused with the reason and the rest carry on
- [x] Move the processing into a Web Worker so the page stays responsive on large batches (`web/src/worker.js`; falls back to the page; both paths in the CI smoke test)
- [x] Build the upload and progress screens, and a results table with overlays
- [x] Photo guidance on the site: print at actual size, whole sheet in frame with all four markers, even light, no flash; and the message shown when a photo has no sheet
- [x] Download particles.csv, summary.csv, run.json (with the review decisions) and NOTE.txt
- [x] Download the overlay images (`overlays.zip`), the particle crops (`crops.zip`) and an HTML summary (`summary.html`: counts, flags, review progress, each photo's overlay)
- [x] Prepare hosting on Cloudflare Pages ([HOSTING.md](HOSTING.md)): `scripts/build_site.mjs` builds `dist/` with OpenCV.js served with the site, the backgrounds, and `_headers` (strict security policy, caching); upload limits 60 MB / 60 MP (`web/src/limits.js`); CI runs the app on the built site under its headers. Stays on the user's GitHub and Cloudflare accounts (November 18).
- [ ] Connect the repository in the Cloudflare dashboard (the owner's account; steps in HOSTING.md)
- [x] Keep the browser and Python versions within about a pixel; an exact match is not needed now (November 18)
- [x] Run the tests on every push (GitHub Actions: pipeline, ruler reader, browser parity tests, plan in sync)
- [ ] Add the licences (decided November 18: MIT for code, CC BY 4.0 for contributed photos and labels) and contribution notes
- [ ] Write the methods page: class definitions, calibration, accuracy and known limits
- [ ] Tag version 1.0 with a changelog
- [ ] Pilot with two or three outside users and collect what confused them (no pilot group identified yet, November 18)
- [ ] Draft a short paper or report and share the repository with the lab group

**In:** The pipeline (parts 1–6), validation results.  
**Out:** A batch tool, a hosted app and a public repository.  
**Watch for:** Community photos will vary far more than lab photos, even on the same printed sheets (printers, paper, phones, light). Plan for quality checks on upload and for retraining with corrected labels.

## 9. Storage

**Goal:** Keep results, labels and model versions in one place, safely and for free.

**Flow:** Rows + review decisions -> Supabase tables + snapshots

Folder: [database/](../database/README.md) (draft schema) and `web/src/storage/` (client).

- [ ] Decide what is stored: full photos, crops only, or only measurement rows (Drive open question 9b). Open, to discuss later. The user's idea: connect the user's Google Drive as the storage, and keep both the full photo and each particle's crop, referenced as columns in the CSV.
- [ ] Set up Supabase: tables for samples, images, particles, labels and model versions, with Row Level Security on every table and no service-role key in client code. A draft is in `database/migrations/0001_draft_schema.sql`.
- [ ] Add reviewer sign-in with Supabase Auth (expert or community role)
- [ ] Save confirmed and corrected labels to Supabase from the review screen
- [ ] Export a versioned database snapshot for each retraining and for publishing
- [ ] Check Supabase free-tier limits and how to keep the project from pausing (open question 9c); set a data retention policy
- [ ] Agree the consent terms for contributed photos and labels (open question 9). The licence is decided: CC BY 4.0
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
- [ ] At each retraining, check the flag thresholds against reviewer corrections (which flagged particles were really wrong, and which wrong ones weren't flagged); change a threshold only by a new, versioned release, never automatically
- [ ] Decide where training runs: a lab GPU machine or free notebooks (open question 8; to be discussed later)
- [ ] Set a plan for who answers issues and retrains the model after the practicum (open question 7)
- [ ] Publish models (GitHub releases, Hugging Face or Zenodo)

**In:** Labelled set (part 7), snapshots (part 9).  
**Out:** Approved model versions for part 5.  
**Watch for:** Community labels vary more than expert labels. Weight them, and keep them out of the gold set.
