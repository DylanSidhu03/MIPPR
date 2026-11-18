# Photographing labelled particles on the MIPPR sheets

**For the lab.** These photos test whether the app gets each particle's **size, colour and shape** right. The particles you already labelled in the ParticleCount spreadsheets are photographed on the printed sheets, and the app's answers are compared with yours, box by box. Nothing needs outlining by hand.

## What you need

- The printed sheets: [backgrounds/](../backgrounds/README.md) (white grid, black grid, checkerboard; Letter or A4)
- A phone with a camera of 12 MP or more
- The labelled particles, still in their wells, and their ParticleCount spreadsheets
- Calipers (for 30–50 particles; see step 5)
- A copy of [templates/well_to_box.csv](templates/well_to_box.csv) for each session

## 1. Print and check the sheets

- Print at **actual size (100%)**, not "fit to page", on matte paper.
- Measure the 100 mm line at the bottom of each sheet with a ruler. If it isn't 100 mm, write down what it measures; the app corrects for it.
- Use a sheet that is flat, clean and not creased.

## 2. Choose the background

| Particles | Sheet |
|---|---|
| Dark (black, brown, dark blue …) | white grid |
| Light, white or clear | black grid |
| Mixed | checkerboard |

**For this test, if time allows, photograph the same particles on all three sheets.** That shows how much the background matters, including the checkerboard (Drive open question 1). If not, use the contrasting sheet for each group and also the checkerboard.

## 3. Place the particles

- **One particle per box**, roughly centred. Keep it off the printed lines and out of the box's top-left corner, where the box label is printed.
- Long fibers may cross a line; note it in the list.
- Work through the wells in order (e.g. W05 → A1, W06 → A2 …), so the list is easy to write.
- **Write each placement in the well-to-box list as you go:** photo file name, box, sample ID and the particle's ID (W05, F03 …). Boxes you leave empty are left out of the list.

## 4. Take the photo

- Hold the phone **flat above the sheet**, roughly overhead. Resting it on a stack of books helps.
- Get the **whole sheet** in the frame: all four black corner squares, the 100 mm line, the grey and white patches, and the **paper's four edges** against a darker surface (the app uses them to catch a printer that scaled the sheet). Fill the frame with the sheet as much as possible.
- **Even, diffuse light, no flash.** No shadows from your hand or phone, and no shiny glare spots on the particles.
- Tap to focus on the sheet. Check the photo is sharp before moving any particle.
- Save the original photo file (no edits, filters or messaging-app compression). Name it so it matches the list, e.g. `EX_01_S01_white_grid_1.jpg`.
- Optional, for a repeatability check: take a second photo of the same sheet after moving the phone slightly.

## 5. Calipers (30–50 particles)

These settle whether the app or the spreadsheet is right where they disagree (the older spreadsheet sizes vary by session). Pick particles of different sizes, shapes and colours, including some near 0.5 mm and some fibers.

- **Length:** the longest distance across the particle.
- **Width:** the narrowest distance across it.

Write them in [templates/calipers.csv](templates/calipers.csv) in mm, with the sample and particle ID.

## 6. New particles (no existing label)

For particles that aren't in a spreadsheet yet, especially film, foam and clear ones, label them in the usual ParticleCount layout ([templates/particle_count.csv](templates/particle_count.csv)): shape and colour per particle. Sizes are optional.

## 7. What to send

- The photos (original files)
- The well-to-box list(s)
- The calipers sheet
- Which ParticleCount spreadsheets the particles come from, and any new label sheets
- The 100 mm line measurement, if it wasn't 100 mm

## How the photos are checked

```bash
python validation/sheet_check.py --photos PHOTOS --boxes well_to_box.csv \
    --lab EX_01_ParticleCount.xlsx --calipers calipers.csv --out results/
```

`results/report.md` gives, per background and per class:
- size agreement
- colour and shape agreement, and which classes get confused
- missed and extra particles
- which warning flags catch wrong sizes

The flag thresholds the app uses are set from this report.
