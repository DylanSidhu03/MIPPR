# Methods

How MIPPR turns a photo of hand-picked particles into measurements and classes, what each class means, how calibration works, how accurate it is so far, and what it cannot do yet. It is written as the basis for a paper's methods section and as a reference for users.

Status: November 18, 2026, app version 0.1.0 (`pipeline/mippr/__init__.py`). Every number below cites the file it comes from. **Provisional** marks a threshold that is a starting value, to be set from labelled sheet photos (`docs/PIPELINE.md`, part 7). The pipeline has so far been tested on synthetic sheet photos and on the lab's older photos, **not yet on real photos of the printed sheets**.

The Python reference pipeline (`pipeline/`) and the browser app (`web/`) implement the same steps; the browser version is checked against Python (section 8.4).

---

## 1. Scope

- **In scope:** particles already hand-picked from the >500 µm fraction, photographed one per box on one of three printed backgrounds. The app measures size and shape and classifies colour and morphology from the image (`CLAUDE.md`; `docs/CLASSIFICATION_SPEC.md`, Scope).
- **Out of scope:** whether a particle is plastic, and its polymer type. That needs FTIR or Raman spectroscopy. Every export includes `NOTE.txt`: *"Visual classification only. Whether a particle is plastic, and its polymer type, were not tested."* The columns `polymer_confirmed` and `polymer_method` are left empty for the lab (`docs/OUTPUT_CSV.md` 4.10).
- **One input type:** a photo without the sheet's corner markers is refused. There is no ruler fallback and no manual scale entry beyond the 100 mm line (section 3.4) (`docs/TECHNICAL_DECISIONS.md`, November 12).
- **Tar-like particles** are not detected; a reviewer can tick a `tar_like` tag (`docs/CLASSIFICATION_SPEC.md` 2).

## 2. Imaging

### 2.1 Printed sheets

The app generates vector PDFs (Letter and A4) in [backgrounds/](../backgrounds/README.md). Users pick the background that contrasts best with their particles.

| Background | Boxes / lines | Intended for |
|---|---|---|
| White grid | white boxes, black lines | dark particles |
| Black grid | black boxes, white lines | light and clear particles |
| Checkerboard | alternating black and white boxes | mixed samples |

Every sheet ("Standard" design, chosen November 5, 2026; `docs/TECHNICAL_DECISIONS.md`, Grid backgrounds):

| Element | Specification |
|---|---|
| Boxes | 12 mm, 0.5 mm lines; 17 × 12 = 204 boxes on Letter, 19 × 11 = 209 on A4 |
| Box labels | Row letter + column number (e.g. `B4`), printed small and mid-grey in each box's top-left corner and in the margin. The label is the particle ID. A 6.5 × 3.2 mm label corner is masked during segmentation. |
| Corner markers | Four ArUco markers, 4x4_50 dictionary, 18 mm. Their IDs encode the background type and paper size. |
| Scale check | A printed 100 mm line in the bottom margin |
| White balance | White and grey patches in the top margin |
| Optional colour patches | A version of each sheet adds six 12 mm patches (red, yellow, green, cyan, blue, magenta), on their own marker IDs (24–47) |

The box size (12 mm) still needs testing with the largest particles and long fibers on real photos (Drive open question 1a).

### 2.2 Paper and printing

- Print at **actual size (100%)**, not "fit to page", on **matte paper** (decided November 18, 2026; `backgrounds/README.md`).
- Printer black, grey and colour rendering do not affect results (section 3.3 and `pipeline/mippr/capture/README.md`, "The printer shouldn't matter").

### 2.3 Photographing

From `backgrounds/README.md`, `web/README.md` and `pipeline/mippr/capture/README.md`:

- One particle per box, in the middle, not touching a line, clear of the box label.
- Roughly overhead, diffuse even light, no flash.
- The whole sheet in frame with **all four corner markers**.
- For the printer-scale check (section 3.4), **all four paper edges** in frame, on a darker surface.
- Resolution at least 10 px/mm. A 12 MP phone with a Letter sheet filling the frame gives about 12–13 px/mm (`pipeline/mippr/capture/README.md`, Photo quality check).

## 3. Calibration

### 3.1 Finding and flattening the sheet

1. **Markers → homography.** The ArUco markers give the background type, paper, scale (px/mm from the marker size) and a homography that removes perspective (`pipeline/mippr/capture/sheet.py`).
2. **Grid-crossing refinement.** Four markers alone cannot correct lens distortion: under strong barrel distortion they leave the grid off by up to about 0.4 of a box. The grid's own line crossings (box corners on the checkerboard) are found in three passes: a wide search, a smooth fit, then a narrow search. Each box is then warped onto a flat grid. On synthetic photos (tilt, barrel distortion up to k1 = −0.04, uneven light, blur, noise, ~10 px/mm) this puts the printed lines within about 0.1 px on all three backgrounds (`docs/TECHNICAL_DECISIONS.md`, Findings from the grid pipeline).
   - On the black grid the outer border is a white line on white paper and cannot be seen; those crossings come from the fit.

### 3.2 Scale

`mm_per_px` comes from the markers (`scale_source = markers`). Every size column scales with it, so a scale error moves every particle by the same factor (`docs/OUTPUT_CSV.md` 4.3).

### 3.3 White balance

Per-channel gains make the printed white patch (the paper white) neutral. The grey patch is only a check: its channel spread after white balance feeds the `color_cast` warning. The coloured patches are only recorded (`run.json`, `white_balance.color_patches_after_bgr`) to compare photos of one printout; they are not a colour standard, because printers render them differently. None of the patches feed a measurement (`docs/TECHNICAL_DECISIONS.md`, November 18, "The printer shouldn't matter").

Segmentation runs on the flattened image before white balance; colour statistics are measured on the white-balanced image (`pipeline/mippr/cli.py`, `run_grid`).

### 3.4 Printer scale

If the printer scaled the sheet ("fit to page"), the markers shrink with everything else, so the marker scale is wrong by the same factor. Two corrections exist (`pipeline/mippr/capture/README.md`; `docs/OUTPUT_CSV.md` 4.11):

| Order | Method | When it applies | Result |
|---|---|---|---|
| 1 | **Entered 100 mm line.** The user measures the printed line with a ruler and enters its true length; sizes scale by length ÷ 100. | Whenever entered (`--line-mm`); wins over the paper edges | `scale_source = user_corrected`, `flag_scale` |
| 2 | **Paper edges.** Letter (215.9 × 279.4 mm) and A4 (210 × 297 mm) are made to size whatever the printer. A radial lens model (one coefficient about the photo centre) is fitted to the grid crossings and marker corners; the photo is flattened onto the sheet plus a 12 mm band; each edge is the strongest dark-to-paper step. Width and height together pick the paper, so an A4 sheet fitted onto Letter is recognised. | All four paper edges in frame, and the scale off by more than 1% | `scale_source = paper_edges`, `flag_scale`, photo problem `printer_scaled` |
| — | Neither | An edge out of frame and no line entered | Marker scale unchanged |

Synthetic results: lens coefficient recovered to 0.002; scale within 0.1% for prints at 94–100%, including A4 fitted onto Letter. Without the lens model, barrel distortion moved the paper edges about 4 mm, because they lie outside the markers (`docs/TECHNICAL_DECISIONS.md`, November 18). Not yet checked on real phone photos (`docs/PIPELINE.md`, part 1).

`flag_scale` is also set when fewer than four markers are found.

### 3.5 Photo quality checks

`check_quality` reports problems with a stable code and a plain message; the run warns and still measures, and `run.json` records the problems and measured values under `quality`. A photo without the sheet is refused. All limits were **set on degraded synthetic photos and are still to be confirmed on real phone photos** (`pipeline/mippr/capture/README.md`).

| Code | Fails when |
|---|---|
| `no_markers`, `marker_missing` | Any corner marker is missing (the message names the corner) |
| `low_resolution` | Under 10 px/mm (a 0.5 mm particle is then under 5 px across) |
| `blurry` | Edge width over 0.30 mm **and** over 4 px |
| `too_dark` | White patch median under 110 |
| `overexposed` | Over 10% of box interiors at ≥ 250, or over half the white patch |
| `glare` | A colourless blob brighter than paper of 0.5 mm² or more inside a box |
| `uneven_light` | Darkest / brightest white box under 0.6 |
| `color_cast` | Grey patch channel spread over 15 grey levels after white balance |
| `printer_scaled` | Paper edges show the printer scaled the sheet by more than 1% |

Known gaps: the uneven-light check does not run on the black grid (no white boxes), and glare on the black grid is only caught where it is brighter than paper (a spot of about 2 mm or more in tests) (`pipeline/mippr/capture/README.md`).

## 4. Segmentation

Classical thresholding against the known background; no model (`pipeline/mippr/segmentation/grid.py`, `edges.py`). Parameter values are the current defaults in `GridSegmentParams`.

1. **Per-box background.** Each box's background colour is the median of its interior, leaving out a 15% border. No empty-board photo is needed.
2. **Difference.** After a Gaussian blur (σ = 1 px), each pixel's difference is the largest absolute colour-channel difference from its own box's background. On the checkerboard each half of a particle across a black/white edge is judged against its own box, so the ImageJ macro's two-pass threshold is not needed (synthetic tests; to be checked on real photos).
3. **Line bridging.** Printed lines (plus a 0.25 mm margin each side) and box-label corners are masked. Across them the difference is bridged from both sides, so a line never becomes a particle, but a fiber crossing it stays in one piece.
4. **Hysteresis threshold.** Seeds above 60, grown through pixels above 25 (grey levels); holes filled; blobs under 9 px dropped.
5. **Half-contrast edge.** Each outline is placed where the difference falls to half the particle's own contrast (the median difference in its core), so bright and faint particles are outlined the same way.
6. **Assignment.** Each blob goes to the box containing its centre: `particle_id` is the box label. Several blobs in one box become `B4-1`, `B4-2`, … (top to bottom, then left to right), each with `flag_multi_blob`.

Touching particles are not split; the one-per-box design avoids them (`pipeline/README.md`, Known gaps).

## 5. Measurements

Deterministic geometry from the outline and scale: the same outline always gives the same numbers. **ImageJ's Analyze Particles is the main guideline for every measurement** (user and advisor, November 18, 2026), so results compare with the lab's workflow; other useful methods are kept as extra columns (`docs/TECHNICAL_DECISIONS.md`; `pipeline/mippr/measurement/geometry.py`).

### 5.1 Main columns (ImageJ definitions)

| Column | ImageJ name | Definition |
|---|---|---|
| `area_mm2` | Area | Pixel count inside the outline × scale² |
| `length_mm` | Feret | Maximum caliper distance, measured over the outer corners of the boundary pixels. **The main size.** |
| `width_mm` | MinFeret | Minimum caliper distance, same convention |
| `perimeter_mm` | Perim. | ImageJ's perimeter of the traced outline |
| `circularity` | Circ. | 4π × area ÷ perimeter² (1 = circle) |
| `aspect_ratio` | AR | Major ÷ minor axis of the fitted ellipse (ported from ImageJ's `EllipseFitter.java`) |
| `roundness` | Round | 4 × area ÷ (π × major axis²) |
| `solidity` | Solidity | Area ÷ convex area |
| `major_mm`, `minor_mm` | Major, Minor | Axes of the ellipse with the particle's area and second moments |

### 5.2 Extra columns

| Column | Definition | Source |
|---|---|---|
| `ced_mm` | Diameter of a circle with the same area | `docs/OUTPUT_CSV.md` 4.3 |
| `convex_area_mm2`, `convex_perimeter_mm` | Area and perimeter of the convex hull | 4.3 |
| `feret_ratio` | `length_mm` ÷ `width_mm`; used by the morphology rules | 4.5 |
| `perimeter_subpixel_mm`, `circularity_subpixel` | From a sub-pixel (marching-squares) outline; the most accurate and least rotation-dependent of five methods tested (worst perimeter error −9.4% vs −12.8% for ImageJ's; `validation/reports/perimeter_study.txt`). Sub-pixel circularity reads about 0.08–0.10 higher than ImageJ's. | 4.5 |
| centroid, bounding box | Location in pixels of the flattened image and in mm | 4.2 |

**Feret bias.** Measured over pixel corners, max Feret is about +1.25 px on a perfect disc at any size; min Feret is exact. At ~10 px/mm that is +0.12 mm: about 6% on a 2 mm particle and about 25% near the 0.5 mm cutoff. On mixed synthetic shapes (discs and rectangles, 10–40 px, 0–45°, blur 0–2 px) the corner method averages −0.12 px (spread 0.99 px); a sub-pixel length averages −0.64 px (spread 0.58 px). ImageJ's convention is kept for comparability; the choice is to be revisited with caliper measurements (`docs/TECHNICAL_DECISIONS.md`, The box-by-box check).

### 5.3 Fiber length and thin particles

- `fiber_length_mm`: the skeleton's longest path, smoothed, with its ends trimmed where it runs into corners and the true end length added back; within about 1–3% on curved and straight test shapes (`pipeline/README.md`). The centre-line length:width only counts for particles that bend (centre line ≥ 1.1 × straight length; `pipeline/mippr/export.py`, `CURVED_RATIO`). For fibers, size classes and summaries use `fiber_length_mm` (`size_length_source`).
- Width under about 2 px: `width_mm` is left empty and `flag_width_unresolved` is set. The lab's fibers are about 24 µm wide (`docs/LAB_DATA.md`), below one pixel on a whole-sheet photo, so fiber widths keep coming from the microscope.

### 5.4 Opacity

`opacity` (0 = see-through, 1 = opaque): how much of the box's known background contrast the particle blocks. On a single background colour it is a lower bound; across a checkerboard edge it is measured directly (`pipeline/mippr/measurement/opacity.py`; README).

### 5.5 Size uncertainty

The outline is redrawn with the edge at 40% (outer) and 60% (inner) of the particle's contrast instead of 50%, giving `length_mm_outer`, `length_mm_inner`, `width_mm_outer`, `width_mm_inner` and `size_uncertainty` = (outer − inner length) ÷ length. Above 0.10 (**provisional**) it sets `flag_size_uncertain`. It is a warning sign, not an error bar (`pipeline/mippr/measurement/uncertainty.py`; `docs/OUTPUT_CSV.md` 4.3).
- On a synthetic sheet photo at 10.7 px/mm, particles under about 1 mm already exceed 0.10; on the lab's old checkerboard sample (24 particles) the median is 0.04 (`docs/TECHNICAL_DECISIONS.md`, November 12).

### 5.6 Colour statistics

Measured inside the outline with one edge pixel removed, after white balance (`docs/OUTPUT_CSV.md` 4.6):
- mean and SD of CIE Lab (`color_L` … `color_b_sd`), and a hex code
- mean R, G, B (0–255) and mean H (0–360°, averaged on the circle), S, V (0–255)

### 5.7 Size classes and size flags

| Rule | Value |
|---|---|
| `size_class` | `<0.5`, `0.5-1`, `1-2`, `2-5`, `>5` mm, on `length_mm` (or `fiber_length_mm` for fibers); each bin includes its lower bound |
| `flag_min_width` | `width_mm` < 0.5 (may have passed the 500 µm sieve) |
| `flag_near_cutoff` | `length_mm` 0.45–0.55 |

The app flags particles by size; it never drops them (`docs/CLASSIFICATION_SPEC.md` 1).

## 6. Classification

### 6.1 Colour (rule-based, provisional)

13 classes: **clear, white, black, grey, blue, green, red, yellow, orange, brown, pink, purple, multicolor**. Rules version `0.1-provisional` (`pipeline/mippr/color/rules.py`, `COLOR_RULES_VERSION`).

1. Every pixel inside the outline (one edge pixel removed) is sorted into a class by CIE lightness L, chroma C and hue h:

   | Pixel class | Rule (provisional) |
   |---|---|
   | white / grey / black | C < 12; white L ≥ 80, black L ≤ 25, grey between |
   | red / pink | h ≥ 345° or < 40°; pink if L > 65 |
   | orange / brown | 40–75°; brown if L < 50 |
   | yellow / brown | 75–105°; brown if L < 50 |
   | green | 105–200° |
   | blue | 200–295° |
   | purple / pink | 295–345°; pink if L > 70 |
   | black (dark chromatic) | L ≤ 15 |

2. The most common class is the label; the next is `color_secondary`, with its share `color_secondary_fraction` (always recorded).
3. **Multicolor:** the second colour covers ≥ 20% (decided) and is clearly different: not a neighbouring shade (e.g. white/grey, red/orange) and at least ΔE 25 (CIE76) apart.
4. **Clear:** opacity under 0.5 (provisional) and nearly colourless. Clear and white are separated by opacity, not colour.
5. **Confidence:** the share of pixels that agree with the label. There is no automatic "unknown"; a reviewer can set one.

These rules have not been fitted: the lab's older photos have a purple-blue cast and clipped backgrounds, and fitting on them gave no gain (section 8.2). They wait for white-balanced sheet photos with coloured particles.

### 6.2 Morphology

Classes (decided November 11, 2026; `docs/CLASSIFICATION_SPEC.md` 2):

| Class | Visual definition | How assigned now |
|---|---|---|
| Fiber | Long and thin, roughly even width | **Rule:** `feret_ratio` ≥ 3 (decided), or the centre-line ratio for particles that bend, or width unresolved |
| Pellet (bead, sphere) | Round or regular, smooth, looks manufactured | **Rule:** circularity > 0.85, solidity > 0.95, `feret_ratio` < 1.3 (provisional) |
| Film | Thin flexible sheet, often see-through | **Rule:** opacity < 0.5 (provisional) and not a fiber; opaque films need the model |
| Fragment | Hard, irregular, broken or angular edges | Default when no rule applies, with confidence 0.5 ("the rules can't tell") |
| Rubbery fragment | Soft, rubbery-looking, usually black | Needs the v3 image model; labelled fragment until then |
| Foam | Spongy or porous, often white | Needs the v3 image model |
| Other | Does not clearly fit a class | Always goes to review |

- Rule confidences are a logistic function of the distance from each threshold, 0.5 at the threshold (`pipeline/mippr/morphology/rules.py`). `morphology_source` records `rule` or `model`.
- The v3 model (crops plus shape values, run in the browser with ONNX Runtime Web) is planned, not built; it may overrule a rule when confident (`pipeline/mippr/morphology/README.md`).
- **Rubbery fragment** becomes its own class only if the model can tell it apart; otherwise the reviewer marks it (advisor, November 18).
- **Fibers are on hold** (advisor, November 18): the lab usually removes fibers by other methods, and fiber photos are to come. The fiber rule is unchanged until then. The lab records some ≥ 3:1 particles as fragments, so the rule may need a thinness condition (`docs/LAB_DATA.md`).
- Lab labels map as: Fragment → fragment; Rubbery Fragment → rubbery_fragment; Fiber, Line → fiber; Line Bundle → fiber + `flag_bundle`; Sphere → pellet.
- Known tendency: small round particles measure solidity 0.87–0.94 at 10 px/mm, under the 0.95 pellet threshold (`docs/PIPELINE.md`, part 5).

### 6.3 Quality flags

Each flag is a True/False column, and `review_reason` lists the true ones (`docs/OUTPUT_CSV.md` 4.8). Besides the size flags (5.7, 5.5) and `flag_scale` (3.4): `flag_edge` (at the grid's or photo's outer edge; kept, not dropped), `flag_line` (reaches a printed line plus 0.25 mm, or a label corner), `flag_multi_blob`, `flag_merged` (solidity < 0.75, provisional), `flag_low_contrast` (contrast < 100 on 0–255, provisional), `flag_bundle` (reviewer). The `flag_low_confidence` threshold is not yet decided.

## 7. Review

Reviewers correct labels and outlines, never numbers, so every measurement traces back to an outline (`docs/OUTPUT_CSV.md` 3; `pipeline/mippr/review/corrections.py`).

| `review_status` | Meaning |
|---|---|
| `auto` | Not reviewed |
| `confirmed` | Reviewed, nothing changed |
| `corrected` | A label was changed or the outline edited |
| `rejected` | Not a particle (dust, hair, paper) or replaced by a split |

- **Originals kept:** a corrected label keeps the prediction in `color_label_original` / `morphology_label_original`. An edited outline is re-measured through the same code as the pipeline (`outline_edited = True`), giving exactly the row the pipeline would produce.
- **Rejected rows kept:** they stay in `particles.csv` (negative examples for training) and are left out of `summary.csv`.
- **Split** (decided, not yet built): pieces of B4 become B4-1, B4-2, …; the original row stays, marked rejected.
- **Order:** flagged and low-confidence particles first, then unflagged, reviewed, rejected.
- `reviewed_by`, `reviewer_role` (`expert` / `community`) and `reviewed_at` record the latest decision; full history is planned for the Supabase `labels` table.

## 8. Accuracy so far

No pass mark has been agreed (Drive open question 6). The validation that will set it, the lab's labelled particles re-photographed on the printed sheets and compared box by box (`validation/sheet_check.py`), has not been run on real photos yet.

### 8.1 Agreement with ImageJ (fragment_area sample)

The lab's old checkerboard photo with an empty-board photo (`validation/legacy/`), 24 particles matched one-to-one, against the lab's own ImageJ results (`validation/results/fragment_area_sample/compare_imagej.txt`):

| Value | Median difference | Middle 80% |
|---|---|---|
| Area | +0.5% | −1.9% to +25.6% |
| Feret | −0.2% | −2.3% to +6.6% |
| MinFeret | +0.1% | −2.2% to +9.4% |
| Perimeter (ImageJ method) | −0.9% | −2.6% to +6.9% |
| Circ. | +3.0% | −0.3% to +5.8% |
| AR | −0.1% | −3.0% to +2.1% |
| Round | +0.2% | −2.0% to +3.1% |
| Solidity | +1.0% | −0.3% to +3.3% |

All 24 particles were found with no false detections (`docs/TECHNICAL_DECISIONS.md`, Findings from the prototype). Large individual differences occur where ImageJ under-measured a particle, e.g. the faint lavender fragment A4-2 (ImageJ 0.34 mm², app 1.90 mm²). This sample is about 75 µm/px, so a 0.5 mm particle is about 7 px across. It uses the legacy board, not the printed sheets.

### 8.2 The lab's older "Rows A–H" photos

20 photos (ruler on white or black paper) paired with the lab's hand-measured spreadsheet rows (`validation/reports/lab_photos.md`):

- 8 photos paired reliably (650 particles; length correlation r = 0.91–1.00).
- The median length difference varies by photo, from +12.4% to −1.7% on the reliable photos. On EX_01_S03 every particle differs by the same factor (1.103), so the outlines agree and only the scale differs (`docs/LAB_DATA.md`). The likeliest cause is the lab's per-session ImageJ scale setting.
- Colour: 96% agreement on white backgrounds (nearly all black particles); 24.5% on black backgrounds (49 particles), where white and pale blue particles read as grey because of a colour cast. Fitting the colour limits gave 90.9% vs 90.8% (88.6% held out), so the rules were not changed.
- Shape: across all 20 photos the app called 90 of the lab's fragments fiber and 57 film.

**Why these photos are not the pass mark:** their scale settings vary by session, they are not white-balanced, and their backgrounds are clipped. They are not app inputs and serve only as a cross-check of the measurement code (`docs/CLASSIFICATION_SPEC.md`, Still open; `docs/TECHNICAL_DECISIONS.md`, November 12).

### 8.3 Synthetic tests

| Test | Result | Source |
|---|---|---|
| Grid flattening (tilt, k1 down to −0.04) | Printed lines within ~0.1 px | `docs/TECHNICAL_DECISIONS.md`, grid pipeline findings |
| Printer scale from paper edges, 94–100% prints | Within 0.1%; lens coefficient to 0.002 | November 18 |
| Detection on synthetic sheet photos | Every contrasting particle found in the right box, no false detections from lines or frame | grid pipeline findings |
| Fiber length along the centre line | Within ~1–3% | `pipeline/README.md` |
| 0.6 mm disc vs resolution | Within 1 px at 9.9–12.4 px/mm; +15% at 8.2 px/mm | `pipeline/mippr/capture/README.md` |
| 0.6 mm disc vs blur | Reads 0.73 mm instead of 0.61 at 1.5 px Gaussian blur | same |

### 8.4 Browser vs Python

Each browser module matches Python exactly or to floating-point precision on identical inputs. End to end, text, labels and flags are identical and numbers agree within about a pixel: OpenCV.js 4.10's flattening differs from OpenCV 5's by up to one grey level, which can flip an edge pixel (≤ 0.3% in area for 2–9 mm particles, 6% for a 0.6 mm particle, up to 0.04 in rule confidences). Within about a pixel was accepted as enough (November 18) (`web/README.md`; `docs/TECHNICAL_DECISIONS.md`, The browser pipeline).

## 9. Known limits and open items

- **Not yet tested on real photos of the printed sheets**: flattening, marker scale against a ruler, paper-edge scale, white balance, quality limits, the 12 mm box size (`docs/PIPELINE.md`, part 1).
- **Low contrast:** a white particle on the white grid (or dark on dark) is not detected; the user must pick the contrasting background. Clear films are the expected worst case (`docs/TECHNICAL_DECISIONS.md`).
- **Thin fibers:** widths are not resolved on whole-sheet photos; detecting them as faint lines is still to build.
- **Small particles:** the Feret bias (5.2) and edge ambiguity (5.5) are largest near the 0.5 mm cutoff, so `flag_near_cutoff` and size classes there are least certain.
- **Checkerboard:** particles across a black/white edge work in synthetic tests only; on one synthetic 5.8 px/mm A4 checkerboard photo the corner refinement moved outer crossings up to 2.3 px, depending on the OpenCV build (`docs/TECHNICAL_DECISIONS.md`, The browser pipeline).
- **Provisional thresholds:** colour rules, pellet/film/fiber thresholds, `flag_merged` 0.75, `flag_low_contrast` 100, `flag_size_uncertain` 0.10, all quality-check limits. Each is to be set from labelled sheet photos and changed only in a new, versioned release (`docs/PIPELINE.md`, part 7).
- **Not built:** v3 morphology model, particle crops, outline redrawing and splitting on the review screen, overlay download, Supabase storage (open question 9b).
- **Open questions:** the validation pass mark (6), checkerboard vs lined grids (1), how the lab measures length and width, who maintains the app (7), where training runs (8).

## 10. Reproducibility

- **Deterministic geometry:** sizes, shapes and colour values come from fixed formulas on the outline; only judgement calls (morphology beyond the rules, from v3) use a model.
- **Versions:** each row carries `app_version`, `color_rules_version` and `model_version` (`docs/OUTPUT_CSV.md` 4.11). Each run writes `run.json` with the MIPPR version, background, paper, layout, markers found, px/mm and mm/px, the printed-line entry, printer scale, white-balance gains and patch values, quality problems and metrics, and the segmentation parameters (`pipeline/mippr/cli.py`, `_write` / `run_grid`).
- **Software:** OpenCV.js 4.10.0 pinned by version and hash in the browser; the Python reference uses OpenCV 5 (`web/README.md`). Builds of OpenCV's distance transform without Intel IPP change fiber lengths by about 1e-6 (`docs/TECHNICAL_DECISIONS.md`).
- **Tests:** pipeline, ruler reader and browser parity tests run on every push (`.github/workflows/tests.yml`).
- **Licences (decided November 18, 2026):** MIT for code; CC BY 4.0 for contributed photos and labels. Licence files are not yet in the repository (`docs/PIPELINE.md`, part 8).
- **Data:** the lab's ParticleCount spreadsheets and photos may be used and published (advisor, November 18); they are kept in Drive, not in this repository (`validation/README.md`).
