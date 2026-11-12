# Part 2: Segmentation

Find each particle in its box and draw its outline. Errors here carry into every measurement and label.

**Method:** threshold against the known background. No model.

## In → Out

| In (from part 1) | Out (to parts 3–5) |
|---|---|
| Flattened grid image, layout, `px_per_mm` | `labels`: one integer per particle (0 = background) |
| | `diff`: difference from each pixel's own box background, used for sub-pixel edges |
| | `band`: printed lines and label corners (masked), used for `flag_line` |
| | The box each particle sits in (`box_of`), which becomes `particle_id` |

## What exists

| File | Does |
|---|---|
| `grid.py` | Box-by-box segmentation on the printed grids. Each box's own background colour; lines and label corners bridged so fibers crossing them stay whole; hysteresis threshold; half-maximum edges |
| `edges.py` | The steps every outline goes through: hysteresis threshold, hole filling, half-maximum edge placement |

## To build

- [ ] **Clear and translucent films:** low-contrast outlines are flagged (`flag_low_contrast`) but often incomplete. Try the opposite background, or opacity-aware thresholds.
- [ ] **Thin fibers** (about 24 µm wide, under one pixel on a sheet photo): detect them as faint lines so their length can be measured (`flag_width_unresolved`).
- [ ] **Particle crops** with the background blanked, for the v3 model and possibly for storage (Drive 9b). Planned: `crop_particle` in `../morphology/model.py`.
- [ ] **Test on real phone photos** of the printed sheets, especially particles across a black/white edge on the checkerboard (open question 1).
- [ ] **Check against labelled photos of the sheets** (part 7): detection counted from the well-to-box list (missed particles, extra detections); outlines are looked at where a particle's size or shape came out wrong. No hand-drawn outlines are needed.
- [ ] Optional: compare with a learned segmenter (Cellpose, SAM, a small U-Net), only if the threshold falls short.

## Watch for

Fibers and clear particles are the usual failures. Look at failures by class, not only the average.
