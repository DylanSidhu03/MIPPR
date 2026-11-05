# Printable backgrounds

Grid backgrounds to photograph hand-picked particles on (Drive spec v0.6, "Standard" design chosen November 5, 2026).

| Background | For | Letter | A4 |
|---|---|---|---|
| White grid (white boxes, black lines) | dark particles | [PDF](mippr_white_grid_letter.pdf) | [PDF](mippr_white_grid_a4.pdf) |
| Black grid (black boxes, white lines) | light and clear particles | [PDF](mippr_black_grid_letter.pdf) | [PDF](mippr_black_grid_a4.pdf) |
| Checkerboard | mixed samples | [PDF](mippr_checkerboard_letter.pdf) | [PDF](mippr_checkerboard_a4.pdf) |

**How to use them:**
- Print at **actual size (100%)**, not "fit to page", on matte paper.
- Check the 100 mm line at the bottom with a ruler. If it isn't 100 mm, enter its true length in the app (`--line-mm` in the prototype).
- Place one particle per box, in the middle, not touching a line and clear of the small box label in the top-left corner.
- Photograph from roughly overhead in diffuse, even light, no flash, with all four corner markers in the frame.

**What's on each sheet:**
- 12 mm boxes with 0.5 mm lines: 17 × 12 = 204 boxes on Letter, 19 × 11 = 209 on A4
- row letters and column numbers in the margin, and each box's label (e.g. `B4`) printed small and grey in its corner; the label is the particle's ID
- four corner markers (ArUco 4x4_50, 18 mm) that tell the app the background, paper, scale and perspective
- white and grey patches for white balance

The PDFs are vector files, so lines and markers print at the printer's full resolution. They are made by the prototype:

```bash
cd prototype
../.venv/bin/python -m mippr.cli sheet --background white_grid --paper letter --out ../backgrounds/
```
