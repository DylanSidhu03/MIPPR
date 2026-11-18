# Printer test kit

The app should give the same sizes whatever printer printed the sheet. Printer black, grey and colour already change no result. A printer that **scales** the sheet ("fit to page") would make every size wrong by the same factor, so the app measures the scale from the paper's own edges and corrects it (`scale_source = paper_edges`). This kit checks that on real phone photos. It takes about 15 minutes.

## What you need

- A printer and plain matte paper (Letter or A4)
- A ruler with millimetres
- A phone, and a darker surface to lay the sheet on (a desk, a dark cloth): the paper's edges must stand out

## Steps

1. Print one sheet (any of the three, e.g. `backgrounds/mippr_white_grid_letter.pdf`) at **actual size (100%)**.
2. Print the same sheet again with **"fit to page"** (or "shrink to fit") turned on. If your printer doesn't offer it, print at 95% instead.
3. On each sheet, measure the 100 mm line at the bottom with the ruler, to the nearest 0.5 mm, and write it down. On the "fit to page" sheet it is usually 94–97 mm.
4. Lay each sheet flat on the darker surface. Photograph it from roughly overhead, in even light without flash, with **all four edges of the paper** and some of the surface around them in the frame. Take two or three photos per sheet, moving the phone a little between them.
5. Run the check on the photos, giving the ruler length of that sheet's line:

   ```bash
   cd pipeline
   ../.venv/bin/python -m mippr.cli printer ~/photos/IMG_0412.jpg ~/photos/IMG_0413.jpg --line-mm 100 --out ~/printer_check/
   ../.venv/bin/python -m mippr.cli printer ~/photos/IMG_0420.jpg ~/photos/IMG_0421.jpg --line-mm 97 --out ~/printer_check/
   ```

   For each photo it prints the scale it found from the paper's edges, which paper it thinks you used, and the difference from your ruler in percentage points. In `--out` it saves each photo with the edges it found drawn in magenta: check they sit on the real edges of the paper.
6. Note the results in `validation/templates/printer_test.csv` (one row per photo) and send it back.

## What good looks like

- The magenta lines follow the paper's edges all the way along.
- The app's scale agrees with the ruler within about **0.5 percentage points** (a ruler read to 0.5 mm on 100 mm is itself ±0.5).
- The 100% sheet comes out at 99–101% ("nothing to correct"); the "fit to page" sheet at your ruler's value.
- The same sheet gives the same scale on each of its photos (within about 0.2 points).

If it says "no estimate", the message names the edge it couldn't find: take the photo again with more of the surface showing on that side, or on a darker surface. In the app nothing is corrected then, and the 100 mm line you type in is still used.
