# Classification spec (v0.3)

What the pipeline measures and decides for every particle, and what the output looks like. Annotators, the Python pipeline and the web app all follow this. Decisions were made on October 27, 2026 (issue #1). Items marked **provisional** may change once validation data exists. v0.2 (November 2, 2026) merges in the team's Output CSV draft. Units are now mm, and the full column list lives in [OUTPUT_CSV.md](OUTPUT_CSV.md). v0.3 (November 11, 2026) adds section 0 (how each value is obtained from the photo), rule-based morphology from v2, opacity, fiber length along the fiber, rubbery fragment, and the second colour. These follow the standard printed backgrounds and the lab's existing records ([LAB_DATA.md](LAB_DATA.md)).

**Scope.** Particles that were hand-picked from the >500 µm fraction and photographed on a standard background. Always on one of the three printed sheets: white grid, black grid or checkerboard (Drive v0.6, [backgrounds/](../backgrounds/README.md)). A photo without the sheet's corner markers is refused, since the markers give the scale, the flattening and the background type. The lab's older photos are used only to check the measurement code (`validation/`). The app measures and visually classifies them. It does **not** test whether a particle is plastic or which polymer it is; that would need FTIR/Raman.

---

## 0. How each value is obtained from the photo

The printed background makes most of this deterministic: the app knows the scale, the geometry of every box, and the colour behind every particle. Only judgement calls need a model.

| Step | What it produces | Method |
|---|---|---|
| Sample details | sample ID, photo number, date, operator, lab, setup, site | Typed at upload |
| Find the sheet | background type, paper, scale (`mm_per_px`) | Corner markers (their IDs encode the background); 100 mm line checks printer scaling |
| Flatten | a corrected image | Homography from the markers, refined with the grid's own line crossings (removes tilt and lens distortion, ~0.1 px) |
| White balance | colour correction | The printed white and grey patches |
| Find each particle | the **outline** (mask) and its box (`particle_id`) | **Threshold**: difference from the box's own known background colour, hysteresis threshold, half-maximum edge. Printed lines and label corners are masked. |
| Measure | length, width, area, perimeter, convex values, CED, fiber length | **Geometry** from the outline × scale |
| Size uncertainty | `size_uncertainty`, length and width at the outer and inner edge | **Geometry**: the outline redrawn with the edge at 40% and 60% of the particle's contrast; how much the length changes |
| Shape ratios | aspect ratio, circularity, solidity | **Derived** from the measurements |
| Opacity | how much of the background shows through | **Measured**: particle contrast against the known background of its box |
| Colour values | Lab mean and spread, hex, second colour and its share | **Measured** inside the outline after white balance |
| Size class, size flags | `size_class`, `flag_near_cutoff`, `flag_min_width`, `flag_width_unresolved` | **Fixed thresholds** |
| Colour label | one of 13 classes | **Rules** on Lab, opacity and the second colour (v2) |
| Morphology label | one of 7 classes | **Rules** for fiber, pellet and film (v2); **image model** for the rest (v3) |
| Quality flags | edge, line, multi-blob, merged, low contrast, size uncertain, scale, low confidence | **Thresholds** and checks; each threshold is set in testing on labelled particles, then applied unchanged in use |
| Review | confirmed / corrected / rejected, reviewer tags (e.g. tar-like) | **A person** |
| Polymer | `polymer_confirmed`, `polymer_method` | **The lab** (FTIR/Raman), not the app |

## 1. Size

| Rule | Decision |
|---|---|
| Main size | **Longest length (max Feret)**, `length_mm`, for every particle. For fibers, the length along the fiber (`fiber_length_mm`) is used instead in size classes and summaries (decided November 11, 2026); `size_length_source` records which. |
| Fiber length | `fiber_length_mm`: length of the fiber's centre line (skeleton), so curved fibers are not under-measured. Filled for particles classed as fiber. |
| Also reported | Minimum width (`width_mm`) and circular equivalent diameter (`ced_mm`) |
| Size cut | Done by the 500 µm sieve. The app does not drop particles by size, it flags them. |
| Flag: may have passed the sieve | `width_mm < 0.5` → `flag_min_width` |
| Flag: near the cutoff | `length_mm` between 0.45 and 0.55 (±10%) → `flag_near_cutoff` |
| Size classes | `length_mm` (or `fiber_length_mm` for fibers) in bins `<0.5`, `0.5-1`, `1-2`, `2-5`, `>5` (`>5` = above the usual 5 mm microplastic limit) |
| Units | mm for lengths and mm² for areas, everywhere (changed from µm in v0.2) |

At the current photo resolution (about 75 µm per pixel), ±10% is about ±1 pixel, which is roughly the measurement uncertainty.

**Thin fibers.** The lab's fibers are typically about 24 µm wide, below one pixel in a photo of a whole sheet (about 55 µm per pixel for a phone photo of a Letter sheet). The app detects them as faint lines and reports their length. When width is under about 2 pixels, `width_mm` is left empty and `flag_width_unresolved` is set. Fiber widths keep coming from the microscope.

## 2. Morphology

The classes are **fragment, rubbery_fragment, fiber, film, foam, pellet**, plus **other** (unsure). Decided November 11, 2026.

**How they are assigned:**
- **From v2, rules:** fiber, pellet and film are decided from measurements, which the standard background makes reliable (thresholds below are starting values, to be tuned on labelled particles photographed on the sheets).
- **From v3, an image model** decides the rest (fragment, rubbery fragment, foam) and may overrule a rule when it is confident. Each label records whether it came from a rule or the model.

**The lab's labels** ([LAB_DATA.md](LAB_DATA.md)) map as: Fragment → fragment; Rubbery Fragment → rubbery_fragment; Fiber and Line → fiber; Line Bundle and "fiber bundle" → fiber with `flag_bundle`; Sphere → pellet.

| Class | Rule for a person | Measured hint (starting values, tune on labelled data) |
|---|---|---|
| **Fiber** | Long and thin, with a roughly even width along its length | **Rule (v2):** length : width **≥ 3 : 1** (decided), using `fiber_length_mm` and the skeleton width for curved fibers. A fiber whose width can't be resolved counts as a fiber. Bundles get `flag_bundle`. |
| **Pellet** (bead, sphere) | Round or regular, smooth, looks manufactured | **Rule (v2):** circularity > 0.85, solidity > 0.95, aspect ratio < 1.3 (starting values) |
| **Fragment** | Hard, irregular, broken or angular edges | Default for opaque pieces that aren't fibers or pellets (v2); confirmed by the model (v3) |
| **Rubbery fragment** | Soft, rubbery-looking piece, usually black (the lab's second most common class, 1,178 of ~4,600) | Texture; **model only** (v3), trained on the lab's labelled particles re-photographed on the sheets. Until then such particles are labelled fragment. |
| **Film** | Thin, flexible sheet, often see-through | **Rule (v2):** low `opacity` (starting value < 0.5) and not a fiber; opaque films are left to the model (v3) |
| **Foam** | Spongy or porous, often white | Surface texture; **model only** (v3). None appear in the lab's sheets so far. |
| **Other** | Doesn't clearly fit one class | Always goes to review |

- **Example photos:** each class needs 2–3 labelled photos added here. These come from the stage 2 pilot batch.
- **Tar-like particles.** The lab notes about 900 particles as tar-like. The app doesn't detect tar or judge material, but reviewers can tick a `tar_like` tag, saved as a column (decided November 11, 2026).
- **Texture** (smooth vs weathered) is not recorded for now. It needs higher-resolution photos. It may be revisited later.

## 3. Color

There are 13 classes: **clear, white, black, grey, blue, green, red, yellow, orange, brown, pink, purple, multicolor**.

| Rule | Decision |
|---|---|
| Clear vs white | Kept separate, decided by **`opacity`** (decided November 11, 2026): the box's background colour is known from the printed design, so the app measures how much of it shows through. **Clear:** low opacity. **White:** opaque and light. |
| Multicolor | A second color covers **≥ 20%** of the particle's area. The app always records the second colour and its share (`color_secondary`, `color_secondary_fraction`), so a blue particle with 10% red streaks keeps that information even though it is labelled blue. |
| Unclear colours | Rules always choose the nearest class; borderline cases get a low `color_confidence` and go to review. There is no automatic "unknown" class, but a reviewer can set one (the lab uses "unknown" 25 times). |
| Consistency between photos | A **color reference in every frame**. The app corrects white balance from it before measuring color. The v0.4 printable backgrounds carry white and grey patches. Whether hue classes also need colored patches or a commercial card is decided in issue #2. |
| How the app assigns color (v2) | Rule-based ranges in Lab (HSV can be derived from it), fitted to labelled particles photographed with the reference. The output has mean and SD of Lab and a hex code for this. |

- **Swatches:** each class needs a reference swatch and its HSV/Lab range added here once the color reference is settled.

## 4. Review and "unsure"

Each flag is its own True/False column. `review_reason` lists the ones that are True, e.g. `edge;min_width`.

| Flag | When | Available |
|---|---|---|
| `flag_near_cutoff` | `length_mm` is 0.45–0.55 | now |
| `flag_min_width` | `width_mm` < 0.5 | now |
| `flag_low_contrast` | The particle barely differs from the background, as with pale or clear particles, so the outline may be incomplete. The rule is particle contrast < 100 on a 0–255 scale (provisional): on the sample, the pale A4 fragment scored 92 and every other particle 141 or more. | now |
| `flag_edge` | The particle touches the edge of the particle zone or photo. It is kept and flagged, not dropped (changed in v0.2). | now |
| `flag_merged` | Two or more touching particles may be detected as one: solidity < 0.75 (provisional). Two blobs in one box get `flag_multi_blob` | now |
| `flag_scale` | Markers missing, or the user corrected the scale | now |
| `flag_line` | The outline reaches a printed line or box edge (long fibers crossing into the next box) | now |
| `flag_multi_blob` | More than one blob in one box; each gets its own row (`B4-1`, `B4-2`) | now |
| `flag_width_unresolved` | Width under about 2 pixels (thin fibers); `width_mm` left empty | v1 |
| `flag_size_uncertain` | The size depends strongly on where the edge is drawn: the length changes by more than 10% (provisional) between edges at 40% and 60% of the particle's contrast | v1 |
| `flag_bundle` | Fiber bundle (the lab's "Line Bundle" / "fiber bundle"); set by a reviewer, later by the model | v2 / v3 |
| `flag_low_confidence` | Color or morphology confidence is below a threshold, still to be decided | v2 / v3 |

A reviewer sets `review_status` (`auto`, `confirmed`, `corrected`, `rejected`). Corrections keep the original prediction, and rejected rows are left out of the summary but kept for training (see OUTPUT_CSV.md section 4.9).

- Users reject false detections (dust, hair, paper) on the review screen.
- **Every export** includes this statement: *"Visual classification only. Whether a particle is plastic, and its polymer type, were not tested."*
- Spectroscopy columns `polymer_confirmed` and `polymer_method` are in the output. The app leaves them blank, and the lab fills them in.

## 5. Perimeter and circularity (provisional)

Circularity = 4π × area / perimeter². Perimeter can be measured several ways, and the choice changes circularity by up to 0.1. `validation/perimeter_study.py` tested five methods on shapes with known perimeters, drawn the way a camera sees them:

| Method | Perimeter error, worst case | Change with rotation | vs the lab's old ImageJ numbers |
|---|---|---|---|
| **Sub-pixel outline** (`perimeter_mm`, `circularity`) | −9% | under 1.2% | circularity ~0.08–0.10 higher |
| **ImageJ method** (`perimeter_imagej_mm`, `circularity_imagej`) | −13% | 7–9% | matches (same calculation) |
| Pixel-centre contour (old prototype) | −20% | 7–9% | — |
| Pixel-edge length, scikit-image weighted | +33 to +38% | 20–37% | — |

- **Current choice:** report **both**. The sub-pixel values are the headline columns because they are the most accurate. The ImageJ values keep old data comparable.
- **Decide later:** which one the app's summaries use. The decision should follow validation against hand measurements and whatever the lab's published methods need.

## 6. Output

The export files and every column are defined in **[OUTPUT_CSV.md](OUTPUT_CSV.md)**:
- `particles.csv`, one row per particle
- `summary.csv`, one row per sample
- `overlay.png`, `run.json` and `NOTE.txt`

The no-plastic statement goes in `NOTE.txt`, not in the CSV, so the CSV opens cleanly in Excel, R and ImageJ.

**Particle identity** (updated November 4, 2026, for the Drive v0.6 grids):
- `particle_id` is the printed box label, e.g. `B4` (`B4-1`, `B4-2` if a box holds several blobs).
- `picture_label` names the photo, e.g. `S042-P01`.
- `particle_ref` combines the two, e.g. `S042-P01-B4`, and is unique across the sample.
- `image_id` is the technical key for the file.

## Still open

- Example photos per morphology class (from the stage 2 pilot)
- Color swatches and HSV/Lab ranges (once the color reference is settled in issue #2)
- Headline perimeter method (section 5)
- Validation tolerance against hand measurements (project open question 6). **Method:** compare length, width, shape and colour per class on labelled particles photographed on the printed sheets (the lab's labelled particles re-photographed, labels carried over by well), and set the pass mark after seeing the agreement. The match against the lab's older "Rows A–H" photos (November 11–12) is a first check of the measurement code, not the pass mark: their scale settings vary by session.
- How the lab measures length and width, and why width is larger than length in SF_02/SF_03 ([LAB_DATA.md](LAB_DATA.md))
- Rule thresholds for fiber, pellet and film, tuned on labelled particles photographed on the sheets
- Confidence threshold for `flag_low_confidence` (from v2/v3 data)
