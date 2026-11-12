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

## What exists

| File | Does |
|---|---|
| `sheet.py` | The printable sheets (layout, vector PDF, PNG), ArUco marker detection, homography, and refinement from the grid's own line crossings (about 0.1 px in synthetic tests) |
| `calibration.py` | White balance from the printed white patch; the grey patch is checked |
| `board.py` | Legacy: the lab's 12 × 24 checkerboard (chessboard corners, per-square warp) |
| `synthetic.py` | Fake photos (tilt, lens distortion, uneven light, blur, noise) for tests |
| `../../scripts/preview_backgrounds.py` | Renders the sheet design options side by side |
| `../../../backgrounds/` | The printed sheets this part generates |

## To build

- [ ] **Photo quality check** before anything else runs: blur, too dark, glare, all four markers in frame, enough pixels per mm. It gives the user a clear message instead of a bad result (`calibration.py`, planned `check_quality`).
- [ ] **Minimum resolution rule:** pixels per mm needed for the smallest particles (0.5 mm) and for fiber length.
- [ ] **Test on real phone photos** of the printed sheets: flattening, scale against a ruler, white balance.
- [ ] **Colour reference:** decide whether colour patches (not only white and grey) are needed for the colour classes.
- [ ] **Scale fallback** for photos without the printed sheet (a ruler, like the lab's photos): the ruler-tick reader in `validation/lab_photo_check.py` is a starting point.

## Open decisions

- Paper (matte paper or cardstock), and printer black variation (Drive open question 1b)
- Checkerboard vs the two lined grids (open question 1)

## Watch for

Glare and shadows. Fixing them at capture is cheaper than fixing them in code. The lab's photos showed a constant 8–10% size gap that traces to scale. Calibration errors move every particle, so check them first.
