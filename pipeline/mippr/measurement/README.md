# Part 3: Measurement

Turn each outline into size and shape numbers in mm. The same outline always gives the same numbers.

**Method:** geometry. No model.

## In → Out

| In (from parts 1–2) | Out (to parts 4–5 and the export) |
|---|---|
| `labels`, `diff`, the image, `mm_per_px` | One dict per particle with these values (see [docs/OUTPUT_CSV.md](../../../docs/OUTPUT_CSV.md) 4.2–4.5): |
| The expected background behind each pixel | - length (max Feret), width (min Feret), area, perimeter (sub-pixel and ImageJ-compatible), convex area and perimeter, CED, bounding box, centroid |
| | - aspect ratio, circularity, solidity |
| | - fiber length and width along the centre line, and whether the particle is evenly thick |
| | - opacity |
| | - length and width with the edge at 40% and 60% of the particle's contrast, for `size_uncertainty` |
| | - colour statistics (Lab mean and SD) for part 4 |

## What exists

| File | Does |
|---|---|
| `geometry.py` | `measure()`: every size and shape value, ImageJ conventions (pixel-count area, Feret over pixel corners), sub-pixel perimeter by marching squares, colour statistics; calls the files below |
| `fiber.py` | Length along the skeleton's longest path, smoothed, ends trimmed and added back (about 1–3% on test shapes); mean width; even-thickness check |
| `opacity.py` | How much of the known background the particle blocks: a lower bound on one background, measured directly across a checkerboard edge |
| `uncertainty.py` | How much the size depends on where the edge is drawn: the outline redrawn at 40% and 60% of the particle's contrast (always outer ≥ drawn ≥ inner). Gives `size_uncertainty` and `flag_size_uncertain` (export.py) |

## To build

- [ ] **Validate sizes** on the lab's labelled particles photographed on the sheets, against the lab's sizes and 30–50 caliper measurements (part 7). On the lab's older photos the app agreed in shape (r = 0.91–1.00); the size gap there varied by session. The cause still needs the lab's answer.
- [ ] **Set the size-uncertainty threshold** in testing (part 7): the value of `size_uncertainty` above which sizes turn out wrong; 0.10 until then. Fibers may need their own, since their thin ends fade. On a synthetic sheet photo at 10.7 px/mm, particles under about 1 mm already pass 0.10, because a 1 px edge ambiguity is a large share of their length.
- [ ] **Decide the headline perimeter method** (sub-pixel or ImageJ-compatible) after validation.
- [ ] **Opacity on real photos:** check the lower-bound estimate on clear films against the opposite background.
- [ ] **Browser port** notes for part 8: marching squares, skeleton thinning and shortest path aren't in OpenCV.js. The size-uncertainty step uses only threshold, dilate and connected components.

## Watch for

A scale error shifts every particle across the 500 µm line. Check calibration before trusting counts.
