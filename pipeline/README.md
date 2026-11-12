# Python reference pipeline

Parts 1–6 of the project (capture and calibration, segmentation, measurement,
colour, morphology, review), plus the command line and export (part 8). One
sub-folder per part, each with its own README:

| Part | Folder |
|---|---|
| 1. Capture and calibration | [mippr/capture/](mippr/capture/README.md) |
| 2. Segmentation | [mippr/segmentation/](mippr/segmentation/README.md) |
| 3. Measurement | [mippr/measurement/](mippr/measurement/README.md) |
| 4. Colour | [mippr/color/](mippr/color/README.md) |
| 5. Morphology | [mippr/morphology/](mippr/morphology/README.md) |
| 6. Review and correction | [mippr/review/](mippr/review/README.md) |
| 8. Export, command line, batch | `mippr/export.py`, `mippr/cli.py`, `mippr/batch.py` (planned) |

Validation scripts (part 7) are in [../validation/](../validation/README.md).

Every photo is taken on one of the three printed backgrounds (Drive spec v0.6):
white grid, black grid or checkerboard, with one particle per box. The corner
markers give the scale, the flattening and the background type, so a photo
without them is refused. (The lab's older photos are used only to check the
measurement code; that code is in [../validation/](../validation/README.md).)

This is the reference the browser app (part 8, `web/`) is ported from and checked
against, so it uses only operations OpenCV.js has (ArUco
detection included).

## Run it

```bash
python -m venv .venv && .venv/bin/pip install -r pipeline/requirements.txt
cd pipeline

# 1. Print a background (Drive spec v0.6). Ready-made PDFs are in ../backgrounds/.
../.venv/bin/python -m mippr.cli sheet --background white_grid --paper letter --out ../backgrounds/

# 2. Measure a photo of particles on it, one particle per box
../.venv/bin/python -m mippr.cli grid PHOTO.jpg --sample-id S042 --photo 1 \
    --date 2026-11-04 --operator DS --lab "Moore Institute" --setup "phone, overhead" --site "Site 3" --out out/

../.venv/bin/python -m pytest tests
```

### Printable backgrounds ([`backgrounds/`](../backgrounds/README.md))

There are three backgrounds:
- **white grid** (white boxes, black lines), for dark particles
- **black grid** (black boxes, white lines), for light and clear particles
- **checkerboard**, for mixed samples

Each comes in Letter and A4. **Print at actual size (100%).**

Each sheet has:
- the "Standard" design: 12 mm boxes with 0.5 mm lines (204 boxes on Letter, 209 on A4)
- box labels by row letter and column number in the margin, and each box's label (e.g. B4) printed small in its top-left corner; keep particles out of that corner
- four corner markers whose IDs tell the app the background and paper
- white and grey patches for white balance
- a 100 mm line: if it doesn't measure 100 mm, pass `--line-mm` with its true length

Place one particle per box, not touching a line.

### Outputs

The output folder gets:

- `particles.csv`: one row per particle, in mm, with the columns and flags
  defined in [docs/OUTPUT_CSV.md](../docs/OUTPUT_CSV.md). Particles are
  identified by box label (`B4`) and `particle_ref` (`S042-P01-B4`).
- `summary.csv`: one row per sample (counts by size class, length
  distribution, review and flag counts; the morphology and color counts fill
  in once labels exist)
- `overlay.png`: the flattened grid with outlines and box labels
- `run.json`: settings, scale, markers found, white balance and the photo quality check (`quality`: problems and the numbers behind them), so a run can be reproduced
- `NOTE.txt`: the statement that classification is visual only

## How the grid pipeline works

1. **Find the sheet.** Detect the ArUco corner markers, which give the
   background type, paper size, scale and perspective.
2. **Flatten it.** The markers are far from the grid, so under lens
   distortion they can miss the grid lines by up to about 0.4 of a box.
   The grid's own line crossings (checkerboard corners on the checkerboard)
   are found in three passes: a wide search, a smooth fit, then a narrow
   search. Each box is then warped onto a flat grid. In synthetic tests this
   puts the printed lines within about 0.1 px.
3. **White balance** from the printed white patch. The grey patch is checked,
   and the result is recorded in `run.json`.
4. **Segment box by box.** Each box's background color is its median. A pixel
   is compared with its own box's color, so on the checkerboard each half of a
   particle across a black/white edge is judged against its own box. Along the
   lines the difference is bridged from both sides, so a line never becomes a
   particle but a fiber crossing it stays whole. Particles are detected with a
   hysteresis threshold, and each outline is placed where the difference falls
   to half the particle's own contrast, so bright and faint particles get the
   same treatment (`segmentation/edges.py`).
5. **Measure and classify** (spec v0.3; `measurement/`, `color/`, `morphology/`). Measurement
   is deterministic geometry with ImageJ conventions (area as a pixel count, Feret
   diameters over pixel edges): area, convex area and perimeter, a sub-pixel
   perimeter (the most accurate in `validation/perimeter_study.py`) plus an
   ImageJ-compatible one, length and width (max and min Feret), circular
   equivalent diameter, aspect ratio, circularity, solidity, and mean and SD of
   CIE Lab. As well as these:
   - **length along the fiber** (`fiber_length_mm`): the skeleton's longest path,
     smoothed, with its ends trimmed where it runs into corners and the true end
     length added back. It is within about 1–3% on curved and straight test shapes.
   - **opacity**: how much of the known box background the particle blocks. With
     one background colour this is a lower bound; across a checkerboard edge it is
     measured directly.
   - **colour classes**: every pixel is sorted into one of the 13 classes by
     provisional Lab rules, giving the main colour, the second colour and its share.
     It is `multicolor` at 20% or more, unless the two are shades of one colour.
   - **morphology rules (v2)**: fiber (length:width ≥ 3), pellet (round and solid),
     film (see-through). Everything else is fragment with confidence 0.5 until the
     v3 model exists.
6. **Assign and flag.** Each blob goes to the box containing its center.
   Flags: `flag_line` (reaches a line), `flag_multi_blob` (more than one blob
   in a box), `flag_edge` (at the grid's outer edge), plus the size and
   contrast flags.

There are synthetic results in `results/synthetic_grid_sample/`:
- the photo
- its overlay
- the CSVs: 8 particles, including a fiber crossing a line, two blobs in H4
  and a particle cut by the edge

## Checks against the lab's own measurements

These use the lab's older photos (a ruler on paper, and the old 12 × 24
checkerboard with an empty-board photo). They are not app inputs; they only check
that the measurement code agrees with the lab's hand and ImageJ numbers. See
[../validation/](../validation/README.md):
- the old checkerboard sample against the lab's ImageJ results: median area +0.5%,
  Feret −0.2% (`validation/legacy/`, `validation/results/fragment_area_sample/`)
- 20 "Rows A–H" ruler photos against the lab's spreadsheets
  ([report](../validation/reports/lab_photos.md))

## Known gaps

- **The grid pipeline is tested only on synthetic photos.** It needs real
  printed sheets photographed with a phone, including the box-size and
  line-thickness test (Drive open question 1a).
- Touching particles are not split. The grid design avoids them (one
  particle per box); two blobs in a box get `flag_multi_blob`.
- The photo quality check (`capture/calibration.py`, `check_quality`) is tuned on
  synthetic photos only.
- Clear films are the expected worst case and need test photos on the black grid.
- The marching-squares step behind the sub-pixel perimeter uses scikit-image.
  The browser port will need its own version, about 60 lines, because
  OpenCV.js doesn't include it.
- Particle crops (needed for the v3 model and possibly for Supabase, Drive
  9b) are not written yet.
- The colour rules and the fiber, pellet and film thresholds are provisional
  starting values. They need fitting on labelled particles photographed on the sheets.
- The skeleton step uses scikit-image and SciPy; the browser port needs its own
  thinning and a shortest-path search over skeleton pixels.
