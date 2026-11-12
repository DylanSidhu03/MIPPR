# The app against the lab's hand records on 20 "Rows A–H" photos (November 12, 2026)

Made with `validation/run_lab_photos.py validation/lab_photos.csv ...` (photos and sheets from Drive, not committed). Each photo's scale was read automatically from its ruler (`validation/ruler.py`, checked by eye), its particles found and measured with the pipeline's own code, and paired with the sheet's wells: one column per plate row, aligned top to bottom by length so extra specks and missing particles are skipped.

**Reliable** means the pairing can be trusted: length correlation r ≥ 0.9 and no more than 1.3× as many detections as sheet rows. The other photos have many specks or broken outlines, so some of their pairs are wrong; their numbers are shown but not used below.

| Photo | Background | Scale (px/mm) | Found / sheet | Matched | r (length) | Length, app vs lab (median) | Width | Reliable |
|---|---|---|---|---|---|---|---|---|
| EX_01_S01_Rows_A-H | white | 30.66 | 92 / 92 | 92 | 0.980 | +8.4% | +18.4% | yes |
| EX_01_S02_500_1of2_Rows_A-H | white | 19.97 | 217 / 92 | 55 | 0.732 | -31.3% | -59.1% | no |
| EX_01_S03_Rows_A-H | white | 15.95 | 94 / 92 | 92 | 1.000 | +10.6% | +10.6% | yes |
| EX_01_S04_500_1of2_HalfA_ROWS_A-H | white | 30.32 | 98 / 92 | 78 | 0.727 | +0.1% | +2.9% | no |
| EX_01_S05_500_1of1_Rows_A-F | white | 30.51 | 67 / 65 | 62 | 0.928 | +9.7% | +3.3% | yes |
| EX_01_S06_500_HalfSplit_1of2_Rows_A-H | white | 30.60 | 98 / 92 | 91 | 0.967 | +12.4% | +13.0% | yes |
| EX_01_S07_Rows_A-H | white | 30.18 | 96 / 92 | 92 | 0.984 | +11.4% | +14.4% | yes |
| EX_01_S08_Rows_A-H | white | 30.51 | 117 / 92 | 92 | 0.984 | +0.8% | +6.0% | yes |
| EX_01_S09_Plate2of2_Rows_A-H | white | 30.51 | 92 / 92 | 80 | 0.908 | +5.5% | +10.4% | yes |
| EX_02_S01_Rows_A-H | white | 30.30 | 109 / 92 | 74 | 0.728 | +0.3% | +0.3% | no |
| EX_02_S05_ROWS_A-H | white | 31.02 | 172 / 103 | 76 | 0.684 | -0.4% | +12.3% | no |
| EX_02_S08_Rows_A-H | white | 31.00 | 131 / 92 | 90 | 0.949 | -0.6% | -0.6% | no |
| EX_02_S09_ROWS_A-Hjpg | white | 30.82 | 317 / 92 | 29 | 0.736 | +48.0% | -67.2% | no |
| MIPPR_LFB04_06MAR25_Rows_A-B | black | 29.92 | 155 / 12 | 12 | 0.330 | -16.7% | -67.7% | no |
| OC_03_DS1_Rows_A-E | black | 30.14 | 57 / 53 | 49 | 0.980 | -1.7% | -2.2% | yes |
| OC_03_US1_ROWS_A-C | black | 30.04 | 40 / 28 | 15 | 0.856 | -7.1% | -11.1% | no |
| OC_05_DS1_ROWS_A-E | white | 30.87 | 106 / 45 | 29 | 0.463 | +0.6% | -50.6% | no |
| OC_05_US1_ROWS_A-H | black | 30.92 | 113 / 92 | 69 | 0.625 | -3.2% | -16.2% | no |
| OC_06_US1_Rows_A-C | white | 29.95 | 21 / 31 | 16 | 0.678 | -2.7% | -12.9% | no |
| OC_07_US1_ROWS_A-C | white | 30.96 | 38 / 27 | 17 | 0.980 | -3.0% | -4.4% | no |

EX_02_S03 (inch-only ruler) and OC_07_DS1 (no ruler found) were left out; the SF_04 photos have no sheet in Drive.

## Sizes

- On the 8 reliable photos (650 particles), the outlines agree closely with the lab's: r = 0.91 to 1.00 between the app's lengths and the hand lengths.
- **The size gap is not constant.** EX_01_S01, S03, S05, S06 and S07 are 8–12% larger than the sheet; EX_01_S08 (+0.8%), S09 (+5.5%) and OC_03_DS1 (−1.7%) agree within a few percent, and so do EX_02_S08 (−0.6%) and OC_07_US1 (−3.0%) on photos just outside the reliability cut. The ruler scale was read the same way on all of them. The likeliest cause is that the lab's ImageJ scale was set per session and was off on some days; a caliper check on one particle from EX_01_S01 or S07 would settle it.
- Widths differ more than lengths (min Feret vs the lab's hand-drawn width).
- Pairing partly by length makes these numbers a little optimistic (pairs more than 2.7× apart are never kept), so they are upper bounds on agreement.

## Colour

Of 650 particles on reliable photos, 588 are black on a white background, and the app agrees on 96% of all particles on white backgrounds. On black backgrounds it agrees on only 24.5% (49 particles):

- White particles read as grey: their lightness is 56–95 (the white limit is 80).
- The lab's blue particles are pale: chroma 5–13 (the grey limit is 12), so most read as grey.
- Every particle, even black and white ones, has a hue near 300° (a purple-blue cast). These photos aren't white-balanced, and their white backgrounds are clipped.

Fitting the lightness and chroma limits (`validation/fit_colors.py --fit`, leave-one-sample-out) gives no real gain: 90.9% at best against 90.8% now, and 88.6% on held-out samples. **The colour rules stay at `0.1-provisional`.** Moving the chroma limit to catch the pale blues would turn the cast whites blue. The rules need white-balanced photos (the printed sheets' grey patch) and more coloured particles to fit on.

## Shape

The lab's "Rubbery Fragment" mostly reads as fragment (no class of its own yet). Across all 20 photos the app calls 90 of the lab's fragments fiber and 57 film; the lab's fibers are measured separately (F-numbered) and rarely appear on these photos.

## Detection problems seen

- **Specks and edges:** tape, card edges and dust around the disc (left out by keeping the plate's cluster of particles).
- **Broken outlines:** large white particles on black (MIPPR_LFB04) split into pieces.
- **White on white** (OC_06, OC_07): faint particles are missed or partly found.
- **Noise:** EX_01_S02 is a farther shot (20 px/mm) with many specks.
