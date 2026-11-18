# Printable backgrounds

Grid backgrounds to photograph hand-picked particles on (Drive spec v0.6, "Standard" design chosen November 5, 2026).

| Background | For | Letter | A4 | With colour patches |
|---|---|---|---|---|
| White grid (white boxes, black lines) | dark particles | [PDF](mippr_white_grid_letter.pdf) | [PDF](mippr_white_grid_a4.pdf) | [Letter](mippr_white_grid_letter_color.pdf) · [A4](mippr_white_grid_a4_color.pdf) |
| Black grid (black boxes, white lines) | light and clear particles | [PDF](mippr_black_grid_letter.pdf) | [PDF](mippr_black_grid_a4.pdf) | [Letter](mippr_black_grid_letter_color.pdf) · [A4](mippr_black_grid_a4_color.pdf) |
| Checkerboard | mixed samples | [PDF](mippr_checkerboard_letter.pdf) | [PDF](mippr_checkerboard_a4.pdf) | [Letter](mippr_checkerboard_letter_color.pdf) · [A4](mippr_checkerboard_a4_color.pdf) |

**How to use them:**
- Print at **actual size (100%)**, not "fit to page", on matte paper.
- Check the 100 mm line at the bottom with a ruler. If it isn't 100 mm, enter its true length in the app (`--line-mm` in the Python pipeline).
- Place one particle per box, in the middle, not touching a line and clear of the small box label in the top-left corner.
- Photograph from roughly overhead in diffuse, even light, no flash, with all four corner markers in the frame.

**What's on each sheet:**
- 12 mm boxes with 0.5 mm lines: 17 × 12 = 204 boxes on Letter, 19 × 11 = 209 on A4
- row letters and column numbers in the margin, and each box's label (e.g. `B4`) printed small and grey in its corner; the label is the particle's ID
- four corner markers (ArUco 4x4_50, 18 mm) that tell the app the background, paper, scale and perspective
- white and grey patches for white balance
- on the colour-patch versions, six more patches (red, yellow, green, cyan, blue, magenta). They have their own corner markers, so the app knows the patches are there and records their colours after white balance in `run.json` (`color_patches_after_bgr`), to compare photos of the same printout. They don't change any result: every printer prints colours a little differently.

The PDFs are vector files, so lines and markers print at the printer's full resolution. They are made by part 1 of the Python pipeline ([pipeline/mippr/capture/](../pipeline/mippr/capture/README.md)):

```bash
cd pipeline
../.venv/bin/python -m mippr.cli sheet --background white_grid --paper letter --out ../backgrounds/
../.venv/bin/python -m mippr.cli sheet --background white_grid --paper letter --color-patches --out ../backgrounds/
```
