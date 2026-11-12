# Part 1: Capture and calibration

Turn a phone or camera photo into a flat, correctly scaled, colour-corrected image whose grid geometry is known exactly. Every number downstream depends on this part.

**Method:** printed design + geometry. No model.

## In → Out

| In | Out (to part 2) |
|---|---|
| A photo of particles on a printed sheet | `Sheet`: background type, paper, `px_per_mm`, and the mapping that flattens the photo |
| | The flattened grid image (`Sheet.rectify_grid`) |
| | White-balance gains, and how neutral the grey patch came out |
| | `flag_scale` inputs: markers found, printed-line correction |
| | Photo quality problems (`check_quality`): a stable code and a plain message each, recorded in `run.json` |

## What exists

| File | Does |
|---|---|
| `sheet.py` | The printable sheets (layout, vector PDF, PNG), ArUco marker detection, homography, and refinement from the grid's own line crossings (about 0.1 px in synthetic tests) |
| `calibration.py` | White balance from the printed white patch; the grey patch is checked. The photo quality check (`check_quality`, below) |
| `board.py` | Legacy: the lab's 12 × 24 checkerboard (chessboard corners, per-square warp) |
| `synthetic.py` | Fake photos (tilt, lens distortion, uneven light, blur, noise) for tests |
| `../../scripts/preview_backgrounds.py` | Renders the sheet design options side by side |
| `../../../backgrounds/` | The printed sheets this part generates |

## To build

- [x] **Photo quality check** (`check_quality`, below). Still to do: check its limits on real phone photos of the printed sheets, and port it to `web/`.
- [x] **Minimum resolution rule:** 10 px per mm for 0.5 mm particles (below). Fiber length still to check.
- [ ] **Uneven light on the black grid:** it has no white boxes, so the shadow check doesn't run there yet.
- [ ] **Test on real phone photos** of the printed sheets: flattening, scale against a ruler, white balance.
- [ ] **Colour reference:** decide whether colour patches (not only white and grey) are needed for the colour classes.
- [ ] **Scale fallback** for photos without the printed sheet (a ruler, like the lab's photos): the ruler-tick reader in `validation/lab_photo_check.py` is a starting point.

## Photo quality check

`check_quality(photo, sheet=None)` runs on the photo as taken and returns a list of
problems (empty = fine), each with a stable `code` and a short `message` for the person
who took the photo. `measure_quality` gives the numbers behind it; both go into
`run.json` under `quality`. The `grid` command prints the problems as warnings and
measures anyway; if the sheet can't be found it stops, and the error lists the other
problems too. Without a sheet the checks that don't need one run on the whole photo.

| Code | Measures | Fails when |
|---|---|---|
| `no_markers`, `marker_missing` | Which of the four corner markers were found | Any is missing (the message names the corner) |
| `low_resolution` | px per mm, from the marker size | Under 10: a 0.5 mm particle is then under 5 px across |
| `blurry` | Edge width: local contrast / steepest gradient, x and y apart, the sharpest quarter of the edges | Over 0.30 mm **and** over 4 px (no scale: over 6 px) |
| `too_dark` | Median of the white patch (no sheet: the brightest 1% of the photo) | Under 110 |
| `overexposed` | Share of box interiors at 250 or more (no sheet: whole photo); the white patch | Over 10%, or over half the white patch |
| `glare` | Largest colourless blob inside a box brighter than paper can be (1.2 × white patch, or clipped) | 0.5 mm² or more |
| `uneven_light` | Darkest / brightest white box (5th / 95th percentile) | Under 0.6 |
| `color_cast` | Spread of the grey patch's channels after white balance | Over 15 grey levels |

All of it is basic OpenCV (Sobel, dilate, erode, fillPoly, connected components), so it
ports to OpenCV.js as is.

**How the limits were chosen.** Synthetic photos (`synthetic.py`, 600 dpi sheet,
16.5 px per mm, paper at about 200) were degraded and run through the whole grid pipeline,
on all three backgrounds:

- **Blur.** The good photo's edges measure 0.20 mm. With Gaussian blur of 1.5 px
  (0.29 mm) the 0.6 mm disc already reads 0.73 mm instead of 0.61, and at 2 px
  (0.33 mm) 0.73 mm, and bigger particles start to grow (2 mm disc +3–5%); at 3 px (0.40–0.49 mm) it is flagged low contrast. 0.30 mm
  sits between them. Motion blur of 5 px measures 0.31 mm across the motion and fails.
  A pixel-sharp edge measures 2–3 px, so at 10–12 px per mm it already reads about
  0.3 mm. The extra 4 px condition leaves that to the resolution check.
- **Dark.** At a white patch of 125 all particles are found. At 94 the 0.6 mm disc turns
  low contrast, at 70 particles are missed, and at 50 nothing is found. The limit is 110.
- **Resolution.** At 12.4 and 9.9 px per mm the 0.6 mm disc measures within 1 px. At 8.2
  it reads 0.69 mm (+15%). At about 6 px per mm the flattening failed on one test photo
  (white grid with stronger lens distortion). The limit is 10 px per mm: a 12 MP phone with the
  Letter sheet filling the frame gives about 12–13.
- **Every other degradation** (overexposure ×1.25, a glare spot, a shadow over half the
  sheet, a blue-channel curve, a covered marker) gives only its own code. The good
  photos give none. `tests/test_quality.py` checks this for each background.
- **Lab photo** `EX_01_S01_Rows_A-H.jpg` (no sheet, ruler, white paper at 254). It reports
  `no_markers` and `overexposed` (61% of the photo is pure white), and no blur (edge width 5.3 px).

## Open decisions

- Paper (matte paper or cardstock), and printer black variation (Drive open question 1b)
- Checkerboard vs the two lined grids (open question 1)

## Watch for

Glare and shadows. Fixing them at capture is cheaper than fixing them in code. On the black grid, glare is only caught where it is brighter than paper (a spot of about 2 mm or more in tests). The lab's photos showed a constant 8–10% size gap that traces to scale. Calibration errors move every particle, so check them first.
