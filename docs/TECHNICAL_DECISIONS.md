# Technical decisions

Technical choices made in coding sessions, within the conceptual decisions in Google Drive.

**How the two fit together:**
- The team's **Google Drive MIPPR folder** holds the conceptual decisions and is always the most up to date. Its `CLAUDE.md` is copied into this repo's [CLAUDE.md](../CLAUDE.md) whenever it changes.
- This file and the documents it links hold the **technical decisions**, which are made after reviewing Drive.
- If a Drive change conflicts with something here, Drive wins and the technical decision is revisited.

Details live in [CLASSIFICATION_SPEC.md](CLASSIFICATION_SPEC.md), [OUTPUT_CSV.md](OUTPUT_CSV.md) and [prototype/README.md](../prototype/README.md).

## Decisions

### Classification spec (issue #1, October 27, 2026)

- **Size:** the main size is longest length (max Feret). Width (min Feret) and CED are also reported. A particle is flagged if its width is under 0.5 mm (it may have passed the sieve) or its length is 0.45–0.55 mm.
- **Morphology:** fragment, fiber (length:width ≥ 3:1), film, foam, pellet/bead, plus other/unsure. Texture is not recorded for now.
- **Color:** 13 classes (clear, white, black, grey, blue, green, red, yellow, orange, brown, pink, purple, multicolor). Clear and white are kept separate by a rule; multicolor means a second color covers ≥ 20%. A color reference goes in every frame.
- **Plastic:** the app does not judge it. Every export says so in `NOTE.txt`, and the `polymer_confirmed` / `polymer_method` columns are left for the lab.

### Perimeter method (October 27, 2026, provisional)

- The sub-pixel outline is the headline perimeter and circularity. It was most accurate on shapes with known perimeters: worst error 9% versus 13–20%, and under 1.2% change with rotation (`prototype/results/perimeter_study.txt`).
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
- **Merged flag on grids:** solidity only. The area rule is kept for the legacy board.
- **Sheet layout (layout version 1, provisional until open question 1a is tested):**
  - 12 mm boxes and 0.4 mm lines
  - 18 mm ArUco markers (4x4_50 dictionary); their IDs encode the background and paper
  - 17 × 12 boxes on Letter, 19 × 12 on A4
  - the white and grey patches in the top margin, and the 100 mm line in the bottom margin
- **Prototype direction:**
  - The grid pipeline is primary: printable sheet generator, marker detection, refinement from the grid's crossings, and per-box segmentation against each box's own background color (no empty-board photo).
  - The checkerboard + empty-board method stays as `legacy`, for the lab's existing photos.
- **White balance:** per-channel gains that make the printed white patch neutral; the grey patch is checked.
- **Scale:**
  - from the markers
  - if the printed 100 mm line measures differently, its length is entered: sizes scale by length ÷ 100, `scale_source = user_corrected` and `flag_scale` is set
  - `flag_scale` is also set when fewer than 4 markers are found
- **Supabase table layout:** waits for Drive open question 9b (what is stored).

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

## Open technical questions

- Headline perimeter method (after validation).
- Confidence threshold for `flag_low_confidence` (from v2/v3 data).
- Tuning the provisional flag thresholds on more photos.
- Test the grid pipeline on real printed sheets and phone photos, including checking box size and line thickness (Drive 1a).
- Supabase table layout, after Drive 9b.
