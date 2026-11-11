# The lab's existing particle records

Summary of the hand-classification spreadsheets in the Drive folder **ParticleCount** (added November 9, 2026) and the photo folder **microplastics photo**. Read November 11, 2026. This file has totals and patterns only; the data itself stays in Drive.

## What was read

- **11 spreadsheets parsed in full** (4,599 rows): EX_01, EX_02, SF_02, OC_05_07, OC_08_09, PalisadesFire, SealBeach, Win_IDC, HKS_IDC, Angela_IDC, AE_IDC.
- **SF_03** was read as text, not parsed, so it is not in the counts below. It has the same pattern as SF_02: rubbery fragments, fibers with polymer IDs, and width often larger than length.
- **Gyre Library plate-reader sheet**: read as text up to plate 5 (the tool cut it off). It has shape and colour but no sizes or polymer types.
- **Not read yet:** OC_01_03 (its download comes back inline, too large to handle that way).
- **No photos opened yet.** Drive gives no preview, and each photo is 1–3 MB.

## Spreadsheet layout

One row per particle. The columns are mostly the same in every file:
- `SampleID`, `ParticleID`, `ParticleShape`, `ParticleColor`
- `ParticlePolymerType`, `ParticleLength`, `ParticleWidth`, `MatchValue`, `Notes`
- AE_IDC also has `Particle Area (um2)`; SF_02 has `IDfromDataAnalysis`.

Several files also have extra sheets:
- **SampleRatios:** the split fraction counted, used to scale counts up
- **ProjectStatus:** hand-picked / analysed / measured / photographed flags per sample

**Particle IDs** (3,591 W, 795 F, 138 P):
- **W05–W96:** wells of a 96-well plate (rows A–H), the plate that goes into the iS50 FTIR plate reader. W01–W04 hold controls, for example a PA66 fragment and a blue bead.
- **F01, F02, …:** fibers, measured and identified separately on slides.
- **P01, …:** particles in the inter-lab (IDC) samples.
- **LFB / PB / AirBlnk** sample IDs: lab-fortified blanks (PA66 spikes), procedural blanks and air blanks.

Lengths and widths are in µm.

## Shapes

| Lab label | Rows | In our spec |
|---|---|---|
| Fragment | 2,516 | fragment |
| Rubbery Fragment | 1,178 | **no class**: mostly black, in EX_01/02, SF_02/03, OC_08_09 |
| Fiber | 833 | fiber |
| Sphere | 29 | pellet/bead (several are attached to a fragment) |
| Film, Pellet, Line, Line Bundle | Gyre sheet only | film, pellet/bead; **Line and Line Bundle have no class** |
| Foam | 0 | foam |

The notes say **"tar-like particle / fragment" about 900 times**, mostly on black fragments and rubbery fragments, so many black particles are tar, not plastic.

## Colours

The counts are black 2,422, white 1,256, blue 356, orange 116, brown 111, red 99, multicolour 52, green 48, pink 26, purple 8, and unknown 25.

All fit our 13 classes except "unknown". "Multicolor (2+ colors)" matches ours. Clear, grey and yellow never appear. Clear and white may be recorded together as white.

## Sizes

4,063 rows have both length and width.

| | Rows | Median length | Median width | Longest |
|---|---|---|---|---|
| Fragment | 2,210 | 1.36 mm | 0.83 mm | 35 mm |
| Rubbery fragment | 1,140 | 1.24 mm | 0.69 mm | 13.6 mm |
| Fiber | 707 | 3.0 mm | 24 µm | 35 mm |

**Non-fiber particles by their longer side:**

| < 0.5 mm | 0.5–1 mm | 1–2 mm | 2–5 mm | > 5 mm | > 10 mm |
|---|---|---|---|---|---|
| 145 | 943 | 1,288 | 912 | 68 | 14 |

**Width larger than length** happens in 92 rows, all in SF_02 (68 of them in one sample, VV125ST5IN), and often in SF_03. Every other file has length ≥ width throughout. The SF series may record the two in a different order, or along fixed axes. It needs checking before those rows are used for validation.

**Fiber widths:** 612 of 707 are under 50 µm. The current photos are about 75 µm per pixel, so a fiber's width can't be measured from them; its length can.

## Polymer types

Only 297 rows have one, almost all of them fibers:
- polyester group 120, "organic matter" 66, unknown 30
- polyamide 27, PVC group 16, acrylic 16, PP 9, polyolefins 8, plus a few others

Each comes with a `MatchValue` (library match score). Wells sent to the plate reader mostly have no polymer type in these sheets.

## Photos (folder "microplastics photo")

- **580 files**, about 1.4 GB, all JPEG except one TIFF.
- **About 391 are distinct.** Many photos are saved twice: once under the camera timestamp (`IMG_2026_…S.jpg`) and once under a sample name.
- **Sample names match the spreadsheets**, e.g. `EX_01_S01_Rows_A-H.jpg`, `SF_04_TEN_1of2_Rows_A-H.jpg`, `OC_05_US1_ROWS_A-H.jpg`, `PSF_01_RCM1.jpg`, `PlateReader_Gyre_Plate_03.jpg`, `MIPPR_LFB02_14SEP26.jpg`.
- **"Rows A–H"** in a name means the photo shows a well plate or its row layout, so each particle in the photo can be matched to a spreadsheet row by well number.
- **Other sets:**
  - three `CheckerBoard_Test` photos
  - about 35 `NN_Plastic_NBS(_SB).jpg`
  - flow-rate tests (`12GPM High 1000-4750 EFF/INF`)
  - Seal Beach wrackline, Venice Beach fire, bristle mat

## What this means for MIPPR

1. **Open question 4 is answered: a labelled set exists.** About 4,600 particles have shape and colour, and about 4,000 have hand-measured length and width. Many can be matched to photos by sample ID and well. This is the validation set for stage 8 and the starting training set for v3.
2. **The shape classes need a decision** (Drive question 3):
   - Rubbery fragment is the second most common shape and has no class.
   - Line and line bundle have no class either.
   - Sphere maps to pellet/bead.
   - Film and foam barely appear.
3. **Tar.** About 900 particles are noted as tar-like. The app doesn't judge plastic, but a "tar-like" label or flag may be worth having.
4. **How length and width are measured**: by hand in ImageJ, with longest length and the width across it? And is the SF series ordered differently? Both need answering before comparing with our max/min Feret.
5. **The lab images particles in 96-well plate order** (wells A–H × 1–12, W01–W04 for controls). This relates to the printed grid design. The grid sheets could use the plate's own labels, or the plate could be the background.
6. **Fibers are measured and identified on a separate path** from fragments. Their widths are below what the current photos resolve.

## Questions for the lab

- How are ParticleLength and ParticleWidth measured (tool, and which axes)? Why is width larger than length in SF_02/SF_03?
- What is "Rubbery Fragment" (tire wear? rubber?), and should it be its own class?
- Are "Line" and "Line Bundle" (Gyre sheet) the same as fiber and fiber bundle?
- Are the "Rows A–H" photos of the well plate itself, and at what scale (is there a ruler or known well spacing)?
- May the spreadsheets and photos be used as the validation and training set, and under what terms (Drive open question 9)?
