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

There are two methods:
- **grid** (primary): the Drive spec v0.6 printed grid sheets, with one
  particle per box and corner markers
- **legacy**: the lab's existing checkerboard photos, using the
  template-difference idea from
  [fragment_area](https://github.com/Moore-Institute-4-Plastic-Pollution-Res/fragment_area)

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

# The lab's existing photos: particle photo + empty-board photo of the 12 x 24 checkerboard
../.venv/bin/python -m mippr.cli legacy PARTICLE.jpg TEMPLATE.jpg --square-mm 10 --sample-id S042 --out out/

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

`--square-mm` (legacy mode only) is the side of one printed square of the lab's
board. The lab's notes say 1 cm, and the ImageJ results imply 10.07 mm.
**Measure the printed board with a ruler**: every length scales with this
number, and areas with its square.

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
   particle but a fiber crossing it stays whole. Hysteresis threshold and
   half-maximum edges are as in the legacy method.
5. **Measure and classify** (spec v0.3; `measurement/`, `color/`, `morphology/`). As well as the size and shape
   columns:
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

## How the legacy method works (checkerboard + empty-board photo)

1. **Find the board** (`capture/board.py`). OpenCV's chessboard detector finds the
   11 × 23 inner corners, which are then refined to sub-pixel accuracy.
2. **Flatten it.** Each square is warped onto a fixed grid (140 px per square)
   using its own four corners. A single perspective warp left about 3 px of
   error from lens distortion. The per-square warp gets this to 0.1 px, so the
   particle photo and template line up pixel for pixel. Because the grid is
   fixed, the scale is known: µm per px = square size / 140.
3. **Compare with the template** (`segmentation/legacy.py`).
   - Shift the template's brightness square by square to match the particle
     photo. In the sample, blacks were 3× brighter in one shot.
   - Take the largest colour-channel difference.
   - Bridge the difference across each printed square edge, so a mid-tone
     particle lying on a gridline is not cut in two.
   - Detect particles with hysteresis thresholding. Near gridlines, slivers
     under 3 px wide are ignored, because misalignment and colour fringing
     leave thin lines there.
4. **Place the edge.** Each particle's outer outline is set where the
   difference falls to half the particle's own contrast (the half-maximum
   rule), so bright and faint particles get the same treatment. The interior is
   never cut.
5. **Measure** (`measurement/geometry.py`). This is deterministic geometry with ImageJ
   conventions: area as a pixel count, Feret diameters over pixel edges. The
   outputs are:
   - area, convex area and convex perimeter
   - perimeter, from a sub-pixel outline (the most accurate method in
     `validation/perimeter_study.py`), plus an ImageJ-compatible perimeter and
     circularity
   - length and width (max and min Feret)
   - circular equivalent diameter and size class
   - centroid and bounding box (pixels), centroid in mm
   - aspect ratio, circularity and solidity
   - mean and SD of CIE Lab from the mask's interior, plus a hex code
   - the well label (A–L, 1–12) as printed on the board
6. **Export** (`export.py`). Converts to mm and sets the flags (edge,
   merged, near cutoff, min width, low contrast, scale). Writes `particles.csv`
   and `summary.csv` as defined in `docs/OUTPUT_CSV.md`, with review and
   provenance columns ready for the review screen.

## Results on the lab's sample photo

Files are in `results/fragment_area_sample/`. The comparison uses
`validation/compare_imagej.py` against `fragment_area/results/area_results.csv`.

- **Detections.** MIPPR finds 24 particles. ImageJ found 26 objects, which are
  24 particles plus two specks of 1 and 7 px. One of those specks is a piece of
  a particle that ImageJ split in two. No false detections and no misses.
- **Agreement with ImageJ** across the 24 particles:

  | Metric | Median difference | Middle 80% of particles |
  |---|---|---|
  | Area | +0.5% | −1.9% to +25.6% |
  | Max Feret | −0.2% | −2.3% to +6.6% |
  | Min Feret | +0.1% | −2.2% to +9.4% |
  | Perimeter (ImageJ method) | −0.9% | −2.6% to +6.9% |
  | Circularity (ImageJ method) | +3.0% | −0.3% to +5.8% |

  The large area differences are particles where ImageJ's threshold missed part
  of the particle. The clearest case is the pale lavender fragment in A4,
  where ImageJ found 0.34 mm². MIPPR now covers almost all of it, and flags it
  `flag_low_contrast`.
- **Sub-pixel circularity** reads about 0.08–0.10 higher than ImageJ, because
  ImageJ's pixel-staircase outline makes particles look less round. On shapes
  with a known answer the sub-pixel method is the most accurate
  (`validation/reports/perimeter_study.txt`). Which one is the headline number is a
  provisional decision; see spec section 5.
- **Run time** is about 5 s per photo pair on a laptop CPU.

ImageJ is not ground truth either. Validation still needs hand or caliper
measurements of real particles (stage 8 / open question 6).

## Findings that affect the imaging protocol (stage 2)

- **Resolution is the main limit.** These photos come out to about 75 µm per
  px, so a 500 µm particle is only about 7 px across, and edge pixels make up
  a large share of its area. Fibers under about 150 µm wide (2 px) cannot be
  told apart from gridline residue at this resolution. Shooting closer, or at
  a higher resolution, would help more than any code change.
- **The template-difference approach works well.** It needs an empty-board
  photo taken with the same setup. The camera may move a little between shots,
  because the per-square warp absorbs it.
- **Exposure can differ between the two shots**, because it is corrected
  square by square. Fixed lighting still helps colour measurements.
- **The board looks the same rotated 180°**, so photos must be taken with the
  labels upright for well IDs to be right.

## Known gaps

- **The grid pipeline is tested only on synthetic photos.** It needs real
  printed sheets photographed with a phone, including the box-size and
  line-thickness test (Drive open question 1a).
- Touching particles are not split. The grid design avoids them (one
  particle per box); two blobs in a box get `flag_multi_blob`.
- The photo quality check (`capture/calibration.py`, `check_quality`) is tuned on
  synthetic photos only, and runs in grid mode only, not legacy.
- Clear films are the expected worst case and need test photos. The pale A4
  fragment is now outlined but flagged for review.
- The marching-squares step behind the sub-pixel perimeter uses scikit-image.
  The browser port will need its own version, about 60 lines, because
  OpenCV.js doesn't include it.
- Particle crops (needed for the v3 model and possibly for Supabase, Drive
  9b) are not written yet.
- The colour rules and the fiber, pellet and film thresholds are provisional
  starting values. They still need fitting to the lab's labelled particles.
- The skeleton step uses scikit-image and SciPy; the browser port needs its own
  thinning and a shortest-path search over skeleton pixels.

## Checking against the lab's hand measurements

`validation/lab_photo_check.py` compares the app with the lab's ParticleCount
spreadsheets on their "Rows A–H" layout photos. Those photos show particles laid out
in 8 columns on a white background with a steel ruler. The script reads the scale
from the ruler ticks, finds and measures the particles, matches them to spreadsheet
wells by column and position, and reports agreement. Results are in
[docs/LAB_DATA.md](../docs/LAB_DATA.md).
