# Classification spec (v0.2)

What the pipeline measures and decides for every particle, and what the output looks like. Annotators, the prototype and the web app all follow this. Decisions were made on October 27, 2026 (issue #1). Items marked **provisional** may change once validation data exists. v0.2 (November 2, 2026) merges in the team's Output CSV draft. Units are now mm, and the full column list lives in [OUTPUT_CSV.md](OUTPUT_CSV.md).

**Scope.** Particles that were hand-picked from the >500 µm fraction and photographed on a standard background. Today that is the lab's 12 × 24 checkerboard; the v0.4 imaging plan adds printable white, black and checkerboard backgrounds with corner markers (see CLAUDE.md, stage 2). The app measures and visually classifies them. It does **not** test whether a particle is plastic or which polymer it is; that would need FTIR/Raman.

---

## 1. Size

| Rule | Decision |
|---|---|
| Main size | **Longest length (max Feret)**, `length_mm`. Used in summaries and size classes. |
| Also reported | Minimum width (`width_mm`) and circular equivalent diameter (`ced_mm`) |
| Size cut | Done by the 500 µm sieve. The app does not drop particles by size, it flags them. |
| Flag: may have passed the sieve | `width_mm < 0.5` → `flag_min_width` |
| Flag: near the cutoff | `length_mm` between 0.45 and 0.55 (±10%) → `flag_near_cutoff` |
| Size classes | `length_mm` in bins `<0.5`, `0.5-1`, `1-2`, `2-5`, `>5` (`>5` = above the usual 5 mm microplastic limit) |
| Units | mm for lengths and mm² for areas, everywhere (changed from µm in v0.2) |

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
| `flag_merged` | Two or more touching particles may be detected as one: solidity < 0.75, or area > 3 × the image's median (both provisional) | now |
| `flag_scale` | Markers missing, or the user corrected the scale | now |
| `flag_low_confidence` | Color or morphology confidence is below a threshold, still to be decided | v2 / v3 |

A reviewer sets `review_status` (`auto`, `confirmed`, `corrected`, `rejected`). Corrections keep the original prediction, and rejected rows are left out of the summary but kept for training (see OUTPUT_CSV.md section 4.9).

- Users reject false detections (dust, hair, paper) on the review screen.
- **Every export** includes this statement: *"Visual classification only. Whether a particle is plastic, and its polymer type, were not tested."*
- Spectroscopy columns `polymer_confirmed` and `polymer_method` are in the output. The app leaves them blank, and the lab fills them in.

## 5. Perimeter and circularity (provisional)

Circularity = 4π × area / perimeter². Perimeter can be measured several ways, and the choice changes circularity by up to 0.1. `prototype/scripts/perimeter_study.py` tested five methods on shapes with known perimeters, drawn the way a camera sees them:

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

**Particle identity** (changed in v0.2): `sample_id` + `image_id` + `particle_id`, where `particle_id` is the number drawn on the overlay. `well` (A1–L12) is filled on the labelled checkerboard only.

## Still open

- Example photos per morphology class (from the stage 2 pilot)
- Color swatches and HSV/Lab ranges (once the color reference is settled in issue #2)
- Measured size of a printed square, checked with a ruler
- Headline perimeter method (section 5)
- Validation tolerance against hand measurements (project open question 6)
- Confidence threshold for `flag_low_confidence` (from v2/v3 data)
