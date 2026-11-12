# Technical decisions

Technical choices made in coding sessions, within the conceptual decisions in Google Drive.

**How the two fit together:**
- The team's **Google Drive MIPPR folder** holds the conceptual decisions and is always the most up to date. Its `CLAUDE.md` is copied into this repo's [CLAUDE.md](../CLAUDE.md) whenever it changes.
- This file and the documents it links hold the **technical decisions**, which are made after reviewing Drive.
- If a Drive change conflicts with something here, Drive wins and the technical decision is revisited.

Details live in [CLASSIFICATION_SPEC.md](CLASSIFICATION_SPEC.md), [OUTPUT_CSV.md](OUTPUT_CSV.md) and [pipeline/README.md](../pipeline/README.md).

## Decisions

### Classification spec (issue #1, October 27, 2026)

- **Size:** the main size is longest length (max Feret). Width (min Feret) and CED are also reported. A particle is flagged if its width is under 0.5 mm (it may have passed the sieve) or its length is 0.45–0.55 mm.
- **Morphology:** fragment, fiber (length:width ≥ 3:1), film, foam, pellet/bead, plus other/unsure. Texture is not recorded for now.
- **Color:** 13 classes (clear, white, black, grey, blue, green, red, yellow, orange, brown, pink, purple, multicolor). Clear and white are kept separate by a rule; multicolor means a second color covers ≥ 20%. A color reference goes in every frame.
- **Plastic:** the app does not judge it. Every export says so in `NOTE.txt`, and the `polymer_confirmed` / `polymer_method` columns are left for the lab.

### Perimeter method (October 27, 2026, provisional)

- The sub-pixel outline is the headline perimeter and circularity. It was most accurate on shapes with known perimeters: worst error 9% versus 13–20%, and under 1.2% change with rotation (`validation/reports/perimeter_study.txt`).
- ImageJ-compatible columns are kept alongside, because sub-pixel circularity reads about 0.08–0.10 higher than ImageJ.
- Which one summaries use is decided after validation against hand measurements.

### Output CSV (November 2, 2026)

Merged with the Drive doc "Output CSV: data dictionary and rationale" (Draft 1). Full column list in [OUTPUT_CSV.md](OUTPUT_CSV.md).

- **Units and names:** mm and mm², with plain names (`length_mm`, `width_mm`, `area_mm2`, ...).
- **Files:** `particles.csv` and `summary.csv`, plus `overlay.png`, `run.json` and `NOTE.txt`.
- **Identity:** `image_id` + per-image `particle_id`, with `well` on the labelled checkerboard. *Replaced on November 4, see below.*
- **Sample details:** date, operator, lab, setup and site on every row.
- **Extra columns:** convex area and perimeter, ImageJ-compatible perimeter and circularity, and Lab mean and SD plus a hex code. RGB/HSV statistics, Feret angle and rotated-box size were dropped.
- **Flags:** True/False columns plus a `review_reason` list:
  - edge, merged, low confidence, scale
  - near cutoff, min width, low contrast

  *Line and multi-blob flags added on November 4, see below.*
- **Flag rules (provisional):**
  - merged: solidity < 0.75, or area > 3 × the image's median
  - low contrast: < 100
  - the low-confidence threshold is still to be decided
- **Edge particles** are kept and flagged, not dropped.
- **Review columns:** `review_status` (auto / confirmed / corrected / rejected), original labels, `outline_edited`, reviewer, role and time. Rejected rows stay in `particles.csv` and are left out of the summary.
- **Size classes:** `<0.5`, `0.5-1`, `1-2`, `2-5`, `>5` mm.
- **No "likely plastic" column.**

### Grid backgrounds (Drive v0.6, November 4, 2026)

- **Identity:**
  - `particle_id` is the printed box label, e.g. `B4`.
  - `picture_label` is the sample ID plus photo number, e.g. `S042-P01`, and is shown on the overlay.
  - `particle_ref` combines them, e.g. `S042-P01-B4`, unique across the sample.
  - `image_id` stays as the technical key.
  - `well` is removed, since the box label replaces it.
- **More than one blob in a box:** one row per blob (`B4-1`, `B4-2`, top to bottom then left to right), each with `flag_multi_blob`.
- **Lines:** one `flag_line`, set when the outline reaches a printed line plus a 0.25 mm margin. Fibers crossing into the next box are kept in one piece.
- **`background_type`:** `white_grid`, `black_grid`, `checkerboard`.
- **Merged flag on grids:** solidity only. (The area rule existed only for the lab's old board and went with it on November 12.)
- **Sheet design (November 5, 2026):** the "Standard" design for all three backgrounds, chosen from three options (Compact 10 mm / Standard 12 mm / Large 15 mm boxes). It still needs testing on real photos (Drive open question 1a).
  - 12 mm boxes and 0.5 mm lines
  - each box's label (e.g. `B4`) printed small and mid-grey in its top-left corner, as well as row and column labels in the margin
  - segmentation masks a 6.5 × 3.2 mm label corner in each box, like the lines: the longest label (`M12`) prints 4.5 × 2 mm
  - 18 mm ArUco markers (4x4_50 dictionary); their IDs encode the background and paper
  - 17 × 12 = 204 boxes on Letter, 19 × 11 = 209 on A4
  - the white and grey patches in the top margin, and the 100 mm line in the bottom margin
  - `scripts/preview_backgrounds.py` renders the three design options for comparison
  - the sheets are vector PDFs (about 3 KB each) in [backgrounds/](../backgrounds/README.md), with copies in the Drive folder "Backgrounds"
- **Prototype direction:**
  - The grid pipeline is primary: printable sheet generator, marker detection, refinement from the grid's crossings, and per-box segmentation against each box's own background color (no empty-board photo).
  - The checkerboard + empty-board method stays as `legacy`, for the lab's existing photos. (Superseded November 12: moved to `validation/legacy/`.)
- **White balance:** per-channel gains that make the printed white patch neutral; the grey patch is checked.
- **Scale:**
  - from the markers
  - if the printed 100 mm line measures differently, its length is entered: sizes scale by length ÷ 100, `scale_source = user_corrected` and `flag_scale` is set
  - `flag_scale` is also set when fewer than 4 markers are found
- **Supabase table layout:** waits for Drive open question 9b (what is stored).

### Features and how they are obtained (November 11, 2026)

Decided after reviewing the lab's records ([LAB_DATA.md](LAB_DATA.md)); the standard backgrounds make outlines, sizes and the background colour behind each particle reliable. Details in [CLASSIFICATION_SPEC.md](CLASSIFICATION_SPEC.md) section 0 and [OUTPUT_CSV.md](OUTPUT_CSV.md) section 8b.

- **Morphology:** rules from v2 for fiber, pellet and film; the image model (v3) for fragment, rubbery fragment and foam, and it may overrule a rule.
- **Classes:** fragment, rubbery_fragment, fiber, film, foam, pellet, other. Lab labels: Line → fiber; Line Bundle / fiber bundle → fiber + `flag_bundle`; Sphere → pellet.
- **Opacity** is measured against the known background, and decides clear vs white and helps find films.
- **Fiber length** is measured along the fiber (`fiber_length_mm`) and used for fibers' size class and summaries.
- **Thin fibers:** length is reported; width under about 2 px is left empty with `flag_width_unresolved`.
- **Colour:** nearest class with a confidence, no automatic "unknown"; the second colour and its share are always recorded.
- **Tar:** an optional reviewer tag `tar_like`; no automatic detection.
- **Validation:** match the lab's plate photos to their spreadsheet rows and compare per class; the pass mark is set after.

### What the labelled particles test, and the size check (November 12, 2026)

Decided with the user:
- **The labelled particles test results, not isolation.** They show whether the app gets each particle's size, colour and morphology right, compared box by box with the lab's answer. Finding particles is mostly solved by one particle per box, so there are no hand-drawn outlines; detection is counted from the well-to-box list, and an outline is only looked at when that particle's size or shape came out wrong.
- **Testing sets thresholds; use applies them.** In testing, the known answers show which signals go with wrong results, and each flag's threshold is set from that. In use there are no known answers: the same checks run on every particle with those thresholds, and flagged particles go first in the review list. Reviewer corrections are used to check the thresholds again at each retraining, and a threshold changes only in a new, versioned release.
- **Size check:** `measurement/uncertainty.py` redraws each outline with the edge at 40% and 60% of the particle's contrast (instead of 50%) and records `length_mm_outer`, `length_mm_inner`, `width_mm_outer`, `width_mm_inner` and `size_uncertainty` = (outer − inner length) ÷ length. Above 0.10 (provisional) it sets `flag_size_uncertain`. The outer outline always contains the drawn one and the inner lies within it, keeping every piece that touches the particle (a fiber crossing a line can break at 60%).
  - On synthetic blurred particles the value rises with blur and is largest on small particles: the 40–60% shift is about half the blur width at each end. On the synthetic sheet photo (10.7 px/mm) particles under about 1 mm already pass 0.10, as does the fiber crossing a line, whose thin end fades. Calibration will decide the threshold, possibly a separate one for fibers.
  - On the lab's old checkerboard sample (24 particles) the median is 0.04 and one particle passes 0.10. The faint lavender fragment ImageJ under-measured (A4-2) is not that one: the check measures how ambiguous the edge is relative to the particle's own contrast, and a faint particle can still have a sharp edge. `flag_low_contrast` covers faint particles, so the two flags complement each other; testing will show how much each catches.
- **Caliper reference:** 30–50 particles measured with calipers decide which is right where the app and the lab's sizes disagree.

### Photos are always on one of the three printed backgrounds (November 12, 2026)

Decided by the user: the project runs on the assumption that every photo is taken on one of the three printed backgrounds (white grid, black grid, checkerboard). So:
- **The app has one input.** A photo without the sheet's corner markers is refused, with a message to photograph it on a printed background; the markers give the scale, the flattening and the background type. There is no ruler fallback and no manual scale entry. The only scale correction is the printed 100 mm line (`--line-mm`, `scale_source = user_corrected`).
- **The lab's old 12 × 24 checkerboard is no longer an app mode.** The `legacy` command, `capture/board.py` and `segmentation/legacy.py` moved to `validation/legacy/`, where they only reproduce the lab's earlier setup to compare with its ImageJ results. The shared edge steps (hysteresis, hole filling, half-maximum edges) moved to `segmentation/edges.py`. `measure()` no longer knows about wells or `px_per_square`. `scale_source = checkerboard` and the area rule for `flag_merged` are gone; the database draft now allows only the three background types and `markers` / `user_corrected`.
- **The ruler reader is validation only** (`validation/ruler.py`), used to check the measurement code on the lab's older photos.
- **Labelled data comes from the sheets.** Colour fitting, rule tuning, the v3 training set, the gold set and the pass mark all use photos on the printed sheets. The proposed route: the lab re-photographs its already-labelled particles on the sheets with a well-to-box list, so the hand labels carry over. The lab's older photos stay a cross-check only (their colour cast and per-session scale settings make them unfit as ground truth anyway).
- **Overexposure warning on the lab's old photos:** no longer a question; those photos aren't app inputs.

### Repository organized by the 10 parts (November 12, 2026)

- The plan, the issues (#1–#10) and the folders follow the project's 10 parts: capture and calibration, segmentation, measurement, colour, morphology, review, ground truth and validation, app, storage, and retraining. The old 11-stage plan was folded in, and #11 was closed.
- `prototype/` became `pipeline/`, the Python reference pipeline, with one sub-package per processing part (`mippr/capture`, `segmentation`, `measurement`, `color`, `morphology`, `review`).
- Validation scripts moved to `validation/`.
- `web/`, `database/` and `training/` hold the planned pieces: READMEs, stub modules with their planned signatures, and a draft Supabase schema.
- `web/src/` mirrors the Python parts so each piece can be ported and checked against the Python results (parity tests).
- Proposed, to confirm: plain ES modules with no build step for the web app.

### Browser app foundation (November 12, 2026)

- **Plain ES modules, no build step** (confirmed by going ahead with the build). Cloudflare Pages serves `web/` as it is.
- **OpenCV.js 4.10.0, the official build, pinned by version and hash.** It includes ArUco: `cv.getPredefinedDictionary`, `cv.aruco_DetectorParameters` and `cv.aruco_ArucoDetector` (note the `aruco_` prefix). On synthetic photos its marker corners match Python's `cv2.aruco` to 0 px, in Node and in Chromium. 4.12.0 gives the same; 5.0.0 works but returns marker IDs in a different shape.
  - Missing from 4.10.0 and needed later: `cornerSubPix` (checkerboard crossing refinement) and `boxPoints`. These need small JS versions or a custom build.
  - The page loads the file from jsDelivr with an SRI hash. `web/scripts/fetch_opencv.mjs` downloads the same file for tests (from the npm package `@techstark/opencv-js@4.10.0-release.1`, which is the official file plus a one-line UMD wrapper; sha256 checked). Not committed (10.4 MB).
  - To decide: serve it from jsDelivr or from Cloudflare Pages itself (files up to 25 MiB are allowed).
- **Parity tests:** `node --test web/tests/` compares the JS layout with Python's (within 1e-6 mm), the marker corners, the homography (within 0.01 px) and the rectified sheet (within 1 grey level). Fixtures are generated from the Python pipeline by `web/tests/dump_python_*.py`.
- Functions take `cv` as their first argument, so they have no DOM or global dependency and run in Node for tests.

### Photo quality check (November 12, 2026)

- `check_quality(photo, sheet)` returns problems with a stable code and a plain message; the web app can map the codes to translated text. The run warns and still measures; `run.json` records the problems and the measured values under `quality`.
- Checks and limits (set on degraded synthetic photos, to confirm on real phone photos): markers (names the missing corner), resolution < 10 px/mm, blur (edge width > 0.30 mm and > 4 px), too dark (white patch < 110), overexposed (> 10% of box interiors clipped), glare (≥ 0.5 mm² of colourless pixels brighter than paper), uneven light (darkest/brightest white box < 0.6), colour cast (grey patch spread > 15 after white balance).
- On the lab's existing photos it reports missing markers and overexposure (their white backgrounds are clipped at 254), and no blur.

### Review logic (November 12, 2026)

- `review/corrections.py`: `apply`, `apply_all`, `remeasure`, `review_queue`, `kept`. Reviewers change labels and outlines; an edited outline is re-measured through the same `measure()` and `build_rows()` as the pipeline, so its row is identical to what the pipeline would produce for that outline (tested exactly).
- Status follows from the row: `corrected` if any `*_original` is set or the outline was edited, else `confirmed`. A relabel back to the prediction clears `*_original`. The last decision wins, so a later confirm un-rejects a row.
- Not built: split and merge (need rules for the new particle IDs).
- Gaps in OUTPUT_CSV found while building it: no column says a label was set by a person (`morphology_source` is `rule` or `model`), and only the latest reviewer is kept. The Supabase `labels` table (part 9) holds the full history.

### Ruler scale reader (November 12, 2026)

- `validation/ruler.py` reads the scale from a ruler with no help: it finds the tick edge, tells a millimetre edge from an inch edge by the repeats further in (0.5 → 1 → 5 → 10 mm, versus x2 steps), and refines over hundreds of ticks by autocorrelation. It also returns a mask of the ruler so its ticks and numbers aren't detected as particles.
- On the lab's photos it agrees with the hand-placed reading on EX_01_S01 (30.66 vs 30.67 px/mm) and S03 (15.95 vs 15.99), and was checked by eye on 21 of 22 photos with `--check-image` (one printed number per 10 mm line). It fails on EX_02_S03, whose ruler is inch-only, and finds nothing on OC_07_DS1.
- It is a validation tool only: the app takes photos on the printed sheets, whose markers give the scale.

### Tests on every push (November 12, 2026)

- `.github/workflows/tests.yml`: pipeline tests, the ruler reader's tests, the browser parity tests (with the pinned OpenCV.js fetched and hash-checked), and `scripts/sync_plan.py --check`, which fails if the tracker is out of step with `docs/PIPELINE.md`.

### Repository (October 28 – November 4, 2026)

- The plan, issues and tracker are kept in sync from `docs/PIPELINE.md` with `scripts/sync_plan.py`.
- `scripts-create-issues.sh` was removed, because the issues already exist.
- Work stays on branch `claude/repo-access-600pt5` until a pull request is wanted.

## Findings from the prototype

These are measured on the lab's fragment_area sample (checkerboard plus an empty-board photo).

- **Results:** all 24 particles found, with no false detections. Median agreement with ImageJ: area +0.5%, length −0.2%, width +0.1%, perimeter (ImageJ method) −0.9%.
- **Method:**
  - per-square warp from the detected chessboard corners
  - brightness matched to the template square by square
  - gridline and frame slivers suppressed, with the difference bridged across printed edges
  - hysteresis threshold
  - half-maximum edge placement
- **Resolution:** the sample photos are about 75 µm/px, so a 500 µm particle is only about 7 px across and fibers under ~150 µm wide are lost. Shooting closer helps more than any code change.
- **Lens distortion:** a single homography leaves about 3 px of error. A grid whose crossings are detected (checkerboard corners, or the line crossings of the v0.6 lined grids) corrects it to about 0.1 px. Four corner markers alone cannot.
- **Checkerboard orientation:** it looks the same rotated 180°, so photos must be taken with the labels upright for box IDs to be right.
- **Printed square size:** the notes say 10 mm, and the ImageJ results imply 10.07 mm. To be measured with a ruler.

## Findings from the grid pipeline (synthetic photos, November 4, 2026)

Tested on synthetic photos: perspective tilt, barrel lens distortion up to k1 = −0.04, uneven light, blur and noise, at about 10 px per mm.

- **Flattening:** the corner markers alone leave the grid off by up to about 0.4 of a box under strong distortion. Following the grid's own crossings over three passes (wide search, smooth fit, narrow search) brings printed lines to within about 0.1 px on all three backgrounds.
  - On the black grid the outer border is a white line on white paper and can't be seen; those crossings come from the fit.
- **Segmentation:**
  - Every particle that contrasts with its background is found in the right box, with no false detections from lines or the frame.
  - Fibers crossing a line stay whole and get `flag_line`.
  - Particles cut by the grid's outer edge get `flag_edge`.
- **Low contrast:** a white particle on the white grid (or dark on dark) is not detected. This is why the user picks the contrasting background; `flag_low_contrast` only catches particles that are partly visible.
- **Checkerboard edges:** a particle across a black/white edge is compared with each box's own background, so the ImageJ macro's two-pass threshold is not needed in this test. It still needs checking on real photos.

## Findings from the lab's photos (November 11, 2026)

Two of the lab's "Rows A–H" photos (EX_01_S01, EX_01_S03) were checked against their hand measurements with `validation/lab_photo_check.py`. Details in [LAB_DATA.md](LAB_DATA.md).

- **Detection:** every particle found on both photos, matched to its well by column and position (r = 0.98 and 1.00 between the app's and the hand lengths).
- **Scale gap:** the app's sizes, using the ruler in each photo, are a constant 8% and 10.3% larger than the sheet's. On S03 the ratio is the same for every particle, so the outlines agree and only the scale differs. This needs the lab's answer before the sheets can serve as size ground truth.
- **20 photos (November 12):** [validation/reports/lab_photos.md](../validation/reports/lab_photos.md). On the 8 that pair reliably (650 particles, r = 0.91–1.00) the gap ranges from +12% to −2% by photo, so it comes from the lab's per-session scale, not a constant error in the app. Pairing now aligns each column with its wells by length, skipping specks and missing particles.
- **Colour on these photos:** 96% agreement on white backgrounds (nearly all black particles), 24.5% on black ones. Every particle carries a purple-blue cast and the backgrounds are clipped, so fitting the limits gave nothing (90.9% vs 90.8%; 88.6% held out). The rules stay provisional until white-balanced sheet photos exist.
- **Fiber rule:** the centre-line length:width now only counts for particles that bend (centre line ≥ 1.1 × straight length), because it over-read chunky, elongated fragments. The lab also records some ≥ 3:1 particles as fragments, so the 3:1 rule may need a thinness condition.

## Open technical questions

- The lab's spreadsheets ([LAB_DATA.md](LAB_DATA.md)) raise new ones: classes for rubbery fragment and line/line bundle, how the lab measures length and width, and whether photos match spreadsheet rows by well.

- Headline perimeter method (after validation).
- Confidence threshold for `flag_low_confidence` (from v2/v3 data).
- Tuning the provisional flag thresholds on more photos.
- Test the grid pipeline on real printed sheets and phone photos, including checking box size and line thickness (Drive 1a).
- Supabase table layout, after Drive 9b.
