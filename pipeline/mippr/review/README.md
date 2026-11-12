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

## To build

- [ ] **`corrections.py`** (stubs): apply a decision to a row; re-measure an edited outline; split or merge outlines.
- [ ] **Review order:** low-confidence and flagged particles first (`review_reason`, `flag_low_confidence`).
- [ ] **The review screen** (web, part 8): overlay with outlines, keyboard-friendly accept / reject / relabel, outline redraw.
- [ ] **Who can review:** expert vs community role (sign-in through Supabase Auth, part 9).
- [ ] **Measure review effort:** how many particles need review, and how long it takes (part 7 reports it).
