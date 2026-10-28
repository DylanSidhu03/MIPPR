# Classification spec (v0.1)

What the pipeline measures and decides for every particle, and what the output looks like. Annotators, the prototype and the web app all follow this. Decisions were made on October 27, 2026 (issue #1). Items marked **provisional** may change once validation data exists.

**Scope.** Particles that were hand-picked from the >500 µm fraction and photographed on a standard background. Today that is the lab's 12 × 24 checkerboard; the v0.4 imaging plan adds printable white, black and checkerboard backgrounds with corner markers (see CLAUDE.md, stage 2). The app measures and visually classifies them. It does **not** test whether a particle is plastic or which polymer it is; that would need FTIR/Raman.

---

## 1. Size

| Rule | Decision |
|---|---|
| Main size | **Longest length (max Feret)**, `feret_max_um`. Used in summaries and size classes. |
| Also reported | Minimum width (`feret_min_um`) and circular equivalent diameter (`ced_um`) |
| Size cut | Done by the 500 µm sieve. The app does not drop particles by size, it flags them. |
| Flag: may have passed the sieve | `feret_min_um < 500` → review reason `min_width_below_sieve` |
| Flag: near the cutoff | `feret_max_um` between 450 and 550 µm (±10%) → review reason `near_size_cutoff` |
| Units | µm for lengths and µm² for areas, everywhere |

At the current photo resolution (about 75 µm per pixel), ±10% is about ±1 pixel, which is roughly the measurement uncertainty.

## 2. Morphology

The classes are **fragment, fiber, film, foam, pellet/bead**, plus **other / unsure**.

| Class | Rule for a person | Measured hint (starting values, tune on labelled data) |
|---|---|---|
| **Fiber** | Long and thin, with a roughly even width along its length | Length : width **≥ 3 : 1** (decided). For curved fibers, length is measured along the skeleton, not straight across. |
| **Pellet / bead** | Round or regular, smooth, looks manufactured | High circularity and an aspect ratio near 1 (e.g. circularity > 0.85, aspect ratio < 1.3) |
| **Fragment** | Hard, irregular, broken or angular edges | The usual class for rigid pieces that aren't fibers or pellets |
| **Film** | Thin, flexible sheet, often see-through | Not measurable from above; judged visually, and by the v3 model later |
| **Foam** | Spongy or porous, often white | Surface texture; judged visually, and by the v3 model later |
| **Other / unsure** | Doesn't clearly fit one class | Always goes to review |

- **Example photos:** each class needs 2–3 labelled photos added here. These come from the stage 2 pilot batch.
- **Texture** (smooth vs weathered) is not recorded for now. It needs higher-resolution photos. It may be revisited later.

## 3. Color

There are 13 classes: **clear, white, black, grey, blue, green, red, yellow, orange, brown, pink, purple, multicolor**.

| Rule | Decision |
|---|---|
| Clear vs white | Kept separate. **Clear:** the background shows through, so it looks different on black and white squares; on a black square it looks dark or grey. **White:** opaque, and looks white on either square. |
| Multicolor | A second color covers **≥ 20%** of the particle's area |
| Consistency between photos | A **color reference in every frame**. The app corrects white balance from it before measuring color. The v0.4 printable backgrounds carry white and grey patches. Whether hue classes also need colored patches or a commercial card is decided in issue #2. |
| How the app assigns color (v2) | Rule-based ranges in HSV/Lab, fitted to labelled particles photographed with the reference. The prototype already outputs mean and SD of RGB, HSV and Lab for this. |

- **Swatches:** each class needs a reference swatch and its HSV/Lab range added here once the color reference is settled.

## 4. Review and "unsure"

Each particle gets `review` (yes/no) and `review_reason`, a semicolon-separated list:

| Reason | When | Available |
|---|---|---|
| `near_size_cutoff` | `feret_max_um` is 450–550 µm | now |
| `min_width_below_sieve` | `feret_min_um` < 500 µm | now |
| `low_contrast_outline` | The particle barely differs from the background, as with pale or clear particles, so the outline may be incomplete. The rule is particle contrast < 100 on a 0–255 scale (provisional): on the sample, the pale A4 fragment scored 92 and every other particle 141 or more. | now |
| `touches_gridline` | The outline crosses a printed square edge, where edges are least reliable (checkerboard background only) | now |
| `touches_edge` | The particle touches the edge of the board or photo | now (these are currently left out as tape or frame) |
| `possibly_merged` | Two or more touching particles may be detected as one. Solidity < 0.75 is a provisional rule. | now |
| `low_class_confidence` | Color or morphology confidence is below a threshold | v2 / v3 |

- Users reject false detections (dust, hair, paper) on the review screen.
- **Every export** includes this statement: *"Visual classification only. Whether a particle is plastic, and its polymer type, were not tested."*
- Spectroscopy columns `polymer_confirmed` and `polymer_method` are in the output. The app leaves them blank, and the lab fills them in.

## 5. Perimeter and circularity (provisional)

Circularity = 4π × area / perimeter². Perimeter can be measured several ways, and the choice changes circularity by up to 0.1. `prototype/scripts/perimeter_study.py` tested five methods on shapes with known perimeters, drawn the way a camera sees them:

| Method | Perimeter error, worst case | Change with rotation | vs the lab's old ImageJ numbers |
|---|---|---|---|
| **Sub-pixel outline** (`perimeter_um`, `circularity`) | −9% | under 1.2% | circularity ~0.08–0.10 higher |
| **ImageJ method** (`perimeter_imagej_um`, `circularity_imagej`) | −13% | 7–9% | matches (same calculation) |
| Pixel-centre contour (old prototype) | −20% | 7–9% | — |
| Pixel-edge length, scikit-image weighted | +33 to +38% | 20–37% | — |

- **Current choice:** report **both**. The sub-pixel values are the headline columns because they are the most accurate. The ImageJ values keep old data comparable.
- **Decide later:** which one the app's summaries use. The decision should follow validation against hand measurements and whatever the lab's published methods need.

## 6. Output

An export contains:
- `particles.csv`: one row per particle
- `overlay.png`: the photo with each particle outlined and numbered
- `run.json`: settings, scale and versions
- `NOTE.txt`: the statement in section 4

The statement goes in a separate file, not in the CSV, so the CSV opens cleanly in Excel, R and ImageJ.

**Particle ID:** `{sample_id}-{well}-{n}`, for example `S042-A3-1`. `n` counts particles in the same well, in reading order. Wells exist only on the labelled checkerboard. On plain backgrounds, the well is left blank and the ID becomes `{sample_id}-{n}`.

**CSV columns, in order:**

| Group | Columns |
|---|---|
| Identity | `particle_id`, `sample_id`, `image_file`, `well`, `particle_number` (number shown on the overlay), `x_um`, `y_um` |
| Sample details | `date`, `operator`, `lab`, `setup`, `site` |
| Size (µm, µm²) | `feret_max_um`, `feret_min_um`, `feret_angle_deg`, `ced_um`, `area_um2`, `perimeter_um`, `convex_area_um2`, `convex_perimeter_um` |
| Bounding boxes (µm) | `bbox_width_um`, `bbox_height_um`, `min_rect_length_um`, `min_rect_width_um` |
| Shape (unitless) | `aspect_ratio` (Feret max / min), `circularity`, `solidity` |
| ImageJ-compatible | `perimeter_imagej_um`, `circularity_imagej` |
| Color | `R_mean`, `R_sd`, `G_mean`, `G_sd`, `B_mean`, `B_sd`, `H_mean`, `H_sd`, `S_mean`, `S_sd`, `V_mean`, `V_sd`, `L_mean`, `L_sd`, `a_mean`, `a_sd`, `b_mean`, `b_sd`, `color_px` |
| Classes (blank until v2/v3) | `color_class`, `color_confidence`, `morphology_class`, `morphology_confidence` |
| Review | `review`, `review_reason`, `corrected_by` |
| Lab results (blank) | `polymer_confirmed`, `polymer_method` |
| Reproducibility | `app_version`, `model_version`, `square_mm`, `um_per_px`, `area_px` |

**Notes on the color columns:**
- Hue is 0–360°, averaged as an angle. Saturation and value are 0–255.
- L\* is 0–100, and a\* and b\* are in CIE units.
- Color is taken from the particle's interior, with one edge pixel removed, so the background doesn't mix in.

## Still open

- Example photos per morphology class (from the stage 2 pilot)
- Color swatches and HSV/Lab ranges (once the color reference is settled in issue #2)
- Measured size of a printed square, checked with a ruler
- Headline perimeter method (section 5)
- Validation tolerance against hand measurements (project open question 6)
