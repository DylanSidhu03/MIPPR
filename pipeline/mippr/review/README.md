# Part 6: Review and correction

A person checks the results and fixes what's wrong before export. They can reject false detections (dust, hair), fix an outline, or correct a colour or shape. This keeps errors out of the data, and it is the main source of new training labels.

**Method:** people. This folder holds the rules for applying their decisions; the screen itself is in [web/src/review/](../../../web/src/review/).

## In → Out

| In | Out |
|---|---|
| Particle rows (with flags and `review_reason`), the overlay, and the reviewer's decisions | Updated rows (see [docs/OUTPUT_CSV.md](../../../docs/OUTPUT_CSV.md) 4.9): |
| | - `review_status` (`confirmed` / `corrected` / `rejected`) |
| | - `*_original` labels kept |
| | - `outline_edited` |
| | - reviewer, role and time |
| | - `tar_like` and `flag_bundle` tags |
| | Re-measured values when an outline was edited |
| | Labels for training (part 10) |

## Rules already decided

- Reviewers correct **labels and outlines, never numbers**. An edited outline is re-measured, so every number traces back to an outline.
- A correction keeps the original prediction in `color_label_original` / `morphology_label_original`.
- Rejected rows stay in `particles.csv` (useful as negative examples) and are left out of `summary.csv`.
- Expert-confirmed rows can count more in training and can go into the gold test set (part 10).

## What exists (`corrections.py`)

Plain, deterministic Python, so the review screen can port it line by line. Nothing changes its input; every function returns new rows.

- **`apply(row, decision, context=None)`**: one `Decision` (particle_ref, action, reviewer, role, time, labels / outline / tags) applied to one row.
  - `confirm`: status `confirmed` (or stays `corrected` if earlier corrections stand).
  - `reject`: status `rejected`; the row stays in `particles.csv`.
  - `relabel`: new `color_label` (one of the 13 classes, or `unknown`) and/or `morphology_label` (the 7 classes). The prediction goes to `*_original` on the first correction only; relabelling back to the prediction clears it.
  - `edit_outline`: re-measures the new polygon with `remeasure` and sets `outline_edited`; needs the photo's `MeasureContext`.
  - `tag`: `tar_like` and `flag_bundle` (True/False); `review_reason` is updated. The status is not changed.
  - `split`, `merge`: raise `NotImplementedError` (see below).
  - Status is derived, not stored per action: `corrected` if any `*_original` is set or the outline was edited, otherwise `confirmed`. The latest decision's reviewer, role and time fill `reviewed_by`, `reviewer_role`, `reviewed_at`.
  - Unknown actions, classes, tags or roles, a bad time, or a decision for another particle raise `ValueError`.
- **`remeasure(row, outline, image, mm_per_px, background, **measure_kwargs)`**: rasterises the polygon (vertices at pixel centres, as OpenCV contours) and runs the same `measure()` and `export.build_rows()` as the pipeline, so the pipeline's own mask gives back the pipeline's row exactly (tested on the synthetic grid sample). Keeps identifiers, sample details, review columns, tags, and any label a reviewer already corrected. `MeasureContext` holds what `measure()` was given for the photo.
- **`apply_all(rows, decisions, contexts)`**: decisions in time order; `contexts` maps `image_id` to a `MeasureContext`.
- **`review_queue(rows)`**: unreviewed flagged rows first (any flag, including `flag_size_uncertain` for sizes that depend strongly on where the edge is drawn), then unreviewed unflagged, then reviewed, then rejected. Within the first two groups the lowest colour or morphology confidence comes first (the `flag_low_confidence` threshold isn't decided).
- **`kept(rows)`**: rows that count in `summary.csv`; `export.build_summary` already leaves rejected rows out.

Tests: `tests/test_review.py`.

## To build

- [x] **`corrections.py`**: apply a decision to a row; re-measure an edited outline; review order.
- [ ] **Split and merge**: `remeasure` already measures any mask; still to decide are the new `particle_id`s (B4-1, B4-2?) and what happens to the row merged away (rejected, or removed).
- [ ] **The review screen** (web, part 8): overlay with outlines, keyboard-friendly accept / reject / relabel, outline redraw. It needs to keep each photo's measurement inputs (rectified image, difference map, background image, line mask) to re-measure outlines.
- [ ] **Who can review:** expert vs community role (sign-in through Supabase Auth, part 9).
- [ ] **Review history**: the row keeps only the latest reviewer; the full list of decisions belongs in the Supabase labels table (part 9).
- [ ] **Measure review effort:** how many particles need review, and how long it takes (part 7 reports it).
