# Segmentation and measurement prototype (Python)

Prototype of pipeline stages 3 (segmentation) and 4 (measurement) from
[docs/PROJECT_CONTEXT.md](../docs/PROJECT_CONTEXT.md), built on the lab's
template-difference idea from
[fragment_area](https://github.com/Moore-Institute-4-Plastic-Pollution-Res/fragment_area).
It is here to settle the method before porting it to OpenCV.js for the v1
browser app, so it uses only operations OpenCV.js has.

## Run it

```bash
python -m venv .venv && .venv/bin/pip install -r prototype/requirements.txt
cd prototype
../.venv/bin/python -m mippr.cli PARTICLE.jpg TEMPLATE.jpg --square-mm 10 --out out/
../.venv/bin/python -m pytest tests
```

You need two photos of the 12 × 24 checkerboard: one with particles, one
empty. The output folder gets `particles.csv` (one row per particle),
`overlay.png` (numbered outlines) and `run.json` (settings, scale and version,
so a run can be reproduced).

`--square-mm` is the side of one printed square. The lab's notes say 1 cm, and
the ImageJ results imply 10.07 mm. **Measure the printed board with a ruler**:
every length scales with this number, and areas scale with its square.

## How it works

1. **Find the board** (`board.py`). OpenCV's chessboard detector finds the
   11 × 23 inner corners, which are then refined to sub-pixel accuracy.
2. **Flatten it.** Each square is warped onto a fixed grid (140 px per square)
   using its own four corners. A single perspective warp left about 3 px of
   error from lens distortion. The per-square warp gets this to 0.1 px, so the
   particle photo and template line up pixel for pixel. Because the grid is
   fixed, the scale is known: µm per px = square size / 140.
3. **Compare with the template** (`segment.py`).
   - Shift the template's brightness square by square to match the particle
     photo. In the sample, blacks were 3× brighter in one shot.
   - Take the largest colour-channel difference.
   - Detect particles with hysteresis thresholding. Near gridlines, slivers
     under 3 px wide are ignored, because misalignment and colour fringing
     leave thin lines there.
4. **Place the edge.** Each particle's outline is set where the difference
   falls to half the particle's own contrast (the half-maximum rule), so bright
   and faint particles get the same treatment.
5. **Measure** (`measure.py`). This is deterministic geometry with ImageJ
   conventions: area as a pixel count, Feret diameters over pixel edges. The
   outputs are:
   - area, perimeter, convex area and convex perimeter
   - max and min Feret, and the Feret angle
   - circular equivalent diameter
   - bounding box and minimum-area rectangle
   - aspect ratio, circularity and solidity
   - mean and SD of RGB, HSV (hue averaged as an angle) and CIE Lab, from the
     mask's interior
   - the well label (A–L, 1–12) as printed on the board

## Results on the lab's sample photo

Files are in `results/fragment_area_sample/`. The comparison uses
`scripts/compare_imagej.py` against `fragment_area/results/area_results.csv`.

- **Detections.** MIPPR finds 24 particles. ImageJ found 26 objects, which are
  24 particles plus two specks of 1 and 7 px. One of those specks is a piece of
  a particle that ImageJ split in two. No false detections and no misses.
- **Agreement with ImageJ** across the 24 particles:

  | Metric | Median difference | Middle 80% of particles |
  |---|---|---|
  | Area | +0.0% | −1.9% to +18.8% |
  | Max Feret | −0.2% | −2.3% to +3.2% |
  | Min Feret | −0.1% | −2.3% to +6.2% |

  The large area differences are particles where ImageJ's threshold missed part
  of the particle. The clearest case is the pale lavender fragment in A4:
  ImageJ found 0.34 mm², MIPPR 1.83 mm².
- **Circularity** reads about 5% higher than ImageJ, because ImageJ computes
  perimeter differently. Pick one definition and document it before
  validation.
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

- Touching particles are not split yet, though there are none in the sample.
- There is no blur, darkness or missing-board check on input beyond a clear
  error when the board isn't found.
- The pale or translucent particle in A4 is still only partly outlined. Clear
  films are the expected worst case and need test photos.
- There is no template-free mode yet. A synthetic background could be built
  from the known grid if the lab can't always shoot an empty board.
