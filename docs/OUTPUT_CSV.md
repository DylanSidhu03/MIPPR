# Output CSV: data dictionary

This document defines what the app exports. For each column it gives what the column holds, how it is produced, who creates or changes it, and which release first fills it. Code builds toward this file, and readers of exported files can use it as a reference.

It merges the team's *Output CSV: data dictionary and rationale* (Draft 1, October 28, 2026) with the classification spec decisions ([CLASSIFICATION_SPEC.md](CLASSIFICATION_SPEC.md)). The two were reconciled on November 2, 2026, and updated for the Drive spec v0.6 grid backgrounds on November 4, 2026. The Drive doc holds the conceptual definitions; this file holds the technical details. The prototype in [prototype/](../prototype/README.md) writes exactly these columns.

The app describes particles that have already been hand-picked. It does not decide whether a particle is plastic or identify its polymer, which would need FTIR or Raman. Every export includes `NOTE.txt` saying so.

## 1. What is measured and what is classified

| Variable | Measured or classified | Confidence score? |
|---|---|---|
| Size | Measured: geometry from the outline, converted to mm with the scale | No. It is exact for a given outline. |
| Shape | Measured: ratios from the same outline | No |
| Color values | Measured: average color inside the outline, after white balance | No |
| Color label | Classified by fixed rules (v2) | Yes |
| Morphology label | Classified by a model (v3) | Yes |

## 2. Files in an export

| File | Contents |
|---|---|
| `particles.csv` | One row per detected particle. This is the main output and the source of everything else. |
| `summary.csv` | One row per sample, calculated only from `particles.csv`. This is what researchers usually report. |
| `overlay.png` | The corrected photo with each particle outlined and labelled with its `particle_id` |
| `run.json` | Settings, scale and versions for the run |
| `NOTE.txt` | "Visual classification only. Whether a particle is plastic, and its polymer type, were not tested." |

## 3. Column types and who may change them

| Type | Meaning | Can a user edit it? |
|---|---|---|
| Recorded | Entered by the user, or assigned by the app as bookkeeping | Only the sample details |
| Measured | Calculated from the outline and scale | No. Fix the outline instead, and the app re-measures. |
| Derived | Calculated from other columns | No |
| Classified | A category chosen by rules or a model, with a confidence | Yes, through review. The original prediction is kept in `*_original`. |
| Review | Records what a person did | Set automatically when someone reviews |

Reviewers correct labels and outlines. They never type size or shape numbers, so every measurement stays traceable to an outline.

## 4. Per-particle columns (`particles.csv`)

Columns appear in this order. Empty means "not available in this release" or "not set". True/false columns are written as `True` / `False`.

### 4.1 Identifiers and sample details

| Column | Type | How it is produced | From |
|---|---|---|---|
| `sample_id` | Recorded | Typed at upload | v1 |
| `picture_label` | Recorded | Readable label for the photo: sample ID plus photo number, e.g. `S042-P01`, `S042-P02`. Shown on the overlay. | v1 |
| `image_id` | Recorded | File name plus a short hash of the file, e.g. `particle-3f9c21ab`. This is the unique technical key; image-level settings (scale, background) apply to all its particles. | v1 |
| `particle_id` | Recorded | The printed box label, e.g. `B4` (row letter + column number), unique within the photo. If a box holds more than one blob, they become `B4-1`, `B4-2`, ... (top to bottom, then left to right), and each gets `flag_multi_blob`. On the lab's legacy 12 × 24 checkerboard the well label is used the same way. | v1 |
| `particle_ref` | Recorded | `picture_label` + `particle_id`, e.g. `S042-P01-B4`: unique across the whole sample | v1 |
| `date`, `operator`, `lab`, `setup`, `site` | Recorded | Entered by the user once per upload and repeated on every row, so files from different labs and setups can be combined | v1 |

### 4.2 Location

| Column | Type | How it is produced | From |
|---|---|---|---|
| `centroid_x_px`, `centroid_y_px` | Measured | Center of the outline, in pixels of the corrected image. Places the number on the overlay. | v1 |
| `bbox_x_px`, `bbox_y_px`, `bbox_w_px`, `bbox_h_px` | Measured | Smallest upright box around the outline, in pixels. Used to cut the crop the morphology model sees. | v1 |
| `centroid_x_mm`, `centroid_y_mm` | Measured | The center in mm from the top-left of the board | v1 |

### 4.3 Size (mm)

| Column | Type | How it is produced | From |
|---|---|---|---|
| `length_mm` | Measured | Longest distance across the outline (max Feret) × scale. **The main size.** | v1 |
| `width_mm` | Measured | Narrowest distance across the outline (min Feret) × scale. Key for fibers and for the sieve check. | v1 |
| `area_mm2` | Measured | Pixels inside the outline × scale² | v1 |
| `perimeter_mm` | Measured | Length of the sub-pixel outline × scale (see 4.5) | v1 |
| `ced_mm` | Derived | Diameter of a circle with the same area | v1 |
| `size_class` | Derived | `length_mm` sorted into bins: `<0.5`, `0.5-1`, `1-2`, `2-5`, `>5`. Each bin includes its lower bound. `>5` marks particles above the usual 5 mm microplastic limit. | v1 |
| `convex_area_mm2`, `convex_perimeter_mm` | Measured | Area and perimeter of the convex outline. Saturna reports both; solidity uses the convex area. | v1 |

Length and width follow ImageJ's convention: they are measured over the outer edges of the boundary pixels. Every size column depends on `mm_per_px`. If the scale is wrong, all of them are wrong by the same factor, which is why the printed 100 mm check line exists.

### 4.4 Shape (no units)

| Column | Type | How it is produced | From |
|---|---|---|---|
| `aspect_ratio` | Derived | `length_mm` ÷ `width_mm`. A value of 3 or more counts as a fiber in the spec. | v1 |
| `circularity` | Derived | 4π × area ÷ perimeter² from the sub-pixel outline (1.0 = circle) | v1 |
| `solidity` | Derived | area ÷ convex area. Low values suggest irregular fragments or two merged particles. | v1 |

### 4.5 ImageJ-compatible

| Column | Type | How it is produced | From |
|---|---|---|---|
| `perimeter_imagej_mm` | Measured | Perimeter as ImageJ computes it for traced particles | v1 |
| `circularity_imagej` | Derived | Circularity from that perimeter | v1 |

These keep old ImageJ results comparable. On real particles the sub-pixel `circularity` reads about 0.08–0.10 higher than ImageJ's. Which one is the headline number is still a **provisional decision** (spec section 5).

### 4.6 Color

| Column | Type | How it is produced | From |
|---|---|---|---|
| `color_L`, `color_a`, `color_b` | Measured | Mean CIE Lab inside the outline, with one edge pixel removed, after white balance | v1 |
| `color_L_sd`, `color_a_sd`, `color_b_sd` | Measured | Spread of the same values; high spread suggests a multicolor particle | v1 |
| `color_hex` | Derived | Mean color as a hex code, for a quick look in a spreadsheet | v1 |
| `color_label` | Classified | One of the 13 spec classes (clear, white, black, grey, blue, green, red, yellow, orange, brown, pink, purple, multicolor), assigned by rules; correctable | v2 |
| `color_confidence` | Classified | How clearly the color falls inside one class rather than near a boundary (0–1) | v2 |

### 4.7 Morphology

| Column | Type | How it is produced | From |
|---|---|---|---|
| `morphology_label` | Classified | fragment, fiber, film, foam, pellet or other, from the particle crop plus shape columns; correctable | v3 |
| `morphology_confidence` | Classified | Model probability for its top choice (0–1) | v3 |
| `morphology_runner_up` | Classified | Second choice; helps on borderline cases such as film vs. fragment | v3 |
| `morphology_runner_up_confidence` | Classified | Probability of the second choice. A small gap to the top choice means a genuinely uncertain particle. | v3 |

### 4.8 Quality flags (True / False)

| Column | Rule | From |
|---|---|---|
| `flag_edge` | The outline is within 3 px of the edge of the particle zone (the board) or photo. The particle may be cut off. It is kept, not dropped, so the reviewer decides. | v1 |
| `flag_merged` | Solidity < 0.75, **or** (legacy board only) area > 3 × the image's median particle area, with 3 or more particles. Both thresholds are provisional. On the printed grids only the solidity rule is used: particles sit one per box, sizes on one sheet vary too much for the area rule, and `flag_multi_blob` covers two blobs in a box. | v1 |
| `flag_low_confidence` | Color or morphology confidence below the threshold. The **threshold is still to be decided** from v2/v3 data; empty until then. | v2 / v3 |
| `flag_scale` | Markers not all found, or the user corrected the scale | v1 |
| `flag_near_cutoff` | `length_mm` between 0.45 and 0.55 (±10% of the sieve size) | v1 |
| `flag_min_width` | `width_mm` < 0.5, so the particle may have passed the 500 µm sieve | v1 |
| `flag_low_contrast` | The particle barely differs from the background (contrast < 100 on a 0–255 scale, provisional), so the outline may be incomplete | v1 |
| `flag_line` | The outline reaches a printed line (the line plus a 0.25 mm margin), a box edge on the checkerboard, or the printed label in a box's corner. Common for long fibers that cross into a neighbouring box; they are kept in one piece. | v1 |
| `flag_multi_blob` | More than one blob in the same box (Drive v0.6: one particle per box). Each blob gets its own row. | v1 |
| `review_reason` | Every flag that is True, without the `flag_` prefix, separated by semicolons, e.g. `edge;min_width` | v1 |

### 4.9 Review

| Column | Type | How it is produced | From |
|---|---|---|---|
| `review_status` | Review | `auto` (not reviewed), `confirmed`, `corrected` or `rejected`. Rejected rows stay in `particles.csv`, where they serve as negative examples for training, but are left out of `summary.csv`. | v1 |
| `color_label_original`, `morphology_label_original` | Review | The prediction before a correction; empty if unchanged. The label columns hold the corrected value. | v2 / v3 |
| `outline_edited` | Review | True if the reviewer redrew, split or merged the outline. Measurements then come from the edited outline. | v1 |
| `reviewed_by`, `reviewer_role`, `reviewed_at` | Review | Who reviewed, `expert` or `community`, and when. Expert-confirmed rows can be weighted more in training and used for the gold test set. | v1 |

### 4.10 Lab results

| Column | Type | How it is produced | From |
|---|---|---|---|
| `polymer_confirmed`, `polymer_method` | Recorded | Left empty by the app. The lab fills them in from FTIR/Raman. | v1 |

### 4.11 Provenance

| Column | Type | How it is produced | From |
|---|---|---|---|
| `background_type` | Recorded | `white_grid`, `black_grid` or `checkerboard`, read from the corner marker IDs. The lab's legacy board (no markers) is also `checkerboard`, with `scale_source = checkerboard`. | v1 |
| `mm_per_px` | Recorded | Scale of the corrected image | v1 |
| `scale_source` | Recorded | `markers` (printed sheets), `checkerboard` (legacy board: from the square corners and the entered square size) or `user_corrected` (the printed 100 mm line measured differently and its length was entered) | v1 |
| `app_version`, `color_rules_version`, `model_version` | Recorded | Versions of the code, color rules and model used. The last two are empty until v2/v3. | v1 |
| `processed_at` | Recorded | Date and time of processing (UTC, ISO 8601) | v1 |

## 5. Per-sample summary (`summary.csv`)

All counts leave out rejected particles.

| Column | How it is calculated |
|---|---|
| `sample_id` | From the particle rows |
| `n_images`, `n_particles` | Number of photos, and particles not rejected |
| `count_fragment`, `count_fiber`, `count_film`, `count_foam`, `count_pellet`, `count_other` | Counts by `morphology_label` (corrected labels where they exist); empty until labels exist |
| `count_color_<class>` (13 columns) | Counts by `color_label`; empty until labels exist |
| `count_size_<bin>` (5 columns) | Counts by `size_class` |
| `length_mm_median`, `length_mm_min`, `length_mm_max` | Size distribution |
| `n_reviewed`, `n_corrected`, `pct_human_confirmed` | Rows not `auto`, rows `corrected`, and the percentage of kept rows that are `confirmed` or `corrected` |
| `n_flag_<flag>` (one per flag) | Number of kept particles with each flag. `n_flag_low_confidence` is empty until it exists. |
| `app_version`, `color_rules_version`, `model_version` | Versions used for the sample (several are separated by semicolons) |

## 6. How the columns depend on one another

- **Scale** (`mm_per_px`) → every size column → `aspect_ratio`, `circularity`, `ced_mm`, `size_class`.
- **Outline** → location, size, shape and color values. Editing an outline triggers re-measurement.
- **Shape columns** → inputs to the morphology model. **Color values** → color label. If the models are chained, color label probabilities also feed morphology.
- **Confidences** → `flag_low_confidence` → which rows get reviewed.
- **Review** → corrected and original labels → training data and accuracy tracking for the next model version.
- **Versions** → every label can be traced to the exact rules and model that produced it.

## 7. What each release fills in

| Release | Columns available |
|---|---|
| v1 | Identifiers, sample details, location, size, shape, ImageJ-compatible, color values, quality flags (except low confidence), outline review, provenance |
| v2 | Adds `color_label`, `color_confidence`, `color_label_original`, `color_rules_version` |
| v3 | Adds the morphology columns, `morphology_label_original`, `model_version`, and `flag_low_confidence` |
| v4 | Review columns feed the shared dataset for retraining |

Column names stay the same across releases. Columns not yet available are left empty, so files from different versions can be combined.

## 8. Decisions made when merging (November 2, 2026)

- **Units:** mm and mm², replacing the earlier µm. Flags still use the 500 µm sieve size (0.5 mm).
- **Names:** the draft's plain names (`length_mm`, `width_mm`, ...). This file defines each one.
- **Kept from the spec:**
  - wells
  - sample details on every row
  - convex area and perimeter
  - ImageJ-compatible columns
  - Lab spread
  - flags for near-cutoff, min width and low contrast
  - `polymer_*` columns and `NOTE.txt`
- **Dropped from the spec:**
  - Feret angle, minimum-area rectangle and bounding box in mm
  - RGB/HSV means and SDs
  - `area_px`
  - `touches_gridline`
- **Adopted from the draft:**
  - `image_id`
  - pixel location columns
  - True/False flags, including `flag_scale`
  - runner-up morphology
  - the review columns
  - provenance columns
  - size classes
  - the per-sample summary
  - keeping edge particles (flagged instead of dropped)
- **Rejected particles** stay in `particles.csv` with status `rejected`.
- **November 4, 2026 (Drive v0.6 grids):**
  - `particle_id` is the box label
  - `picture_label` and `particle_ref` added
  - `well` removed, since the box label replaces it
  - `flag_line` and `flag_multi_blob` added, with one row per blob
  - `background_type` values are `white_grid`, `black_grid` and `checkerboard`
  - on grids, the merged flag uses solidity only
- **No "likely plastic" column:** it stays out of scope, unless the lab asks for it.

## 9. Still to be decided

- The confidence threshold for `flag_low_confidence` (from v2/v3 validation data).
- Which perimeter method is the headline circularity (sub-pixel or ImageJ-compatible).
- The provisional thresholds: merged solidity 0.75, merged area 3 × median, low contrast 100.
