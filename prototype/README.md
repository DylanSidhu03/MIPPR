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
../.venv/bin/python -m mippr.cli PARTICLE.jpg TEMPLATE.jpg --square-mm 10 --sample-id S042 \
    --date 2026-10-27 --operator DS --lab "Moore Institute" --setup "phone, overhead" --site "Site 3" --out out/
../.venv/bin/python -m pytest tests
```

You need two photos of the 12 × 24 checkerboard: one with particles, one
empty. The output folder gets:

- `particles.csv`: one row per particle, with the columns and review flags
  defined in [docs/CLASSIFICATION_SPEC.md](../docs/CLASSIFICATION_SPEC.md)
- `overlay.png`: numbered outlines on the photo
- `run.json`: settings, scale and version, so a run can be reproduced
- `NOTE.txt`: the statement that classification is visual only

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
   - Bridge the difference across each printed square edge, so a mid-tone
     particle lying on a gridline is not cut in two.
   - Detect particles with hysteresis thresholding. Near gridlines, slivers
     under 3 px wide are ignored, because misalignment and colour fringing
     leave thin lines there.
4. **Place the edge.** Each particle's outer outline is set where the
   difference falls to half the particle's own contrast (the half-maximum
   rule), so bright and faint particles get the same treatment. The interior is
   never cut.
5. **Measure** (`measure.py`). This is deterministic geometry with ImageJ
   conventions: area as a pixel count, Feret diameters over pixel edges. The
   outputs are:
   - area, convex area and convex perimeter
   - perimeter, from a sub-pixel outline (the most accurate method in
     `scripts/perimeter_study.py`), plus an ImageJ-compatible perimeter and
     circularity
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
  | Area | +0.5% | −1.9% to +25.6% |
  | Max Feret | −0.2% | −2.3% to +6.6% |
  | Min Feret | +0.1% | −2.2% to +9.4% |
  | Perimeter (ImageJ method) | −0.9% | −2.6% to +6.9% |
  | Circularity (ImageJ method) | +3.0% | −0.3% to +5.8% |

  The large area differences are particles where ImageJ's threshold missed part
  of the particle. The clearest case is the pale lavender fragment in A4,
  where ImageJ found 0.34 mm². MIPPR now covers almost all of it, and flags it
  `low_contrast_outline`.
- **Sub-pixel circularity** reads about 0.08–0.10 higher than ImageJ, because
  ImageJ's pixel-staircase outline makes particles look less round. On shapes
  with a known answer the sub-pixel method is the most accurate
  (`results/perimeter_study.txt`). Which one is the headline number is a
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

- Touching particles are not split yet, though there are none in the sample.
- There is no blur, darkness or missing-board check on input beyond a clear
  error when the board isn't found.
- Clear films are the expected worst case and need test photos. The pale A4
  fragment is now outlined but flagged for review.
- The marching-squares step behind the sub-pixel perimeter uses scikit-image.
  The browser port will need its own version, about 60 lines, because
  OpenCV.js doesn't include it.
- There is no template-free mode yet. A synthetic background could be built
  from the known grid if the lab can't always shoot an empty board.
