# Part 7: Ground truth and validation

The known answers that every other part is tuned and judged against: the lab's hand-labelled particles, new labels, and the reports that show whether the app is good enough to trust.

**Method:** labelled data and comparison. Nothing here runs in the app.

**The app only takes photos on the three printed backgrounds**, so the labelled set, the gold set and the pass mark come from photos on the sheets. The lab's older photos (a ruler on white or black paper; the old 12 × 24 checkerboard) are used here only to check the measurement code against the lab's numbers. The quickest route to labelled sheet photos: re-photograph the lab's already-labelled particles on the sheets, one per box, with a list of which well went into which box.

## In → Out

| In | Out |
|---|---|
| Labelled particles photographed on the printed sheets (the lab's labels carried over by well, and new labels) | Tuned thresholds for parts 2–5 |
| The lab's ParticleCount spreadsheets and older photos (Drive; [docs/LAB_DATA.md](../docs/LAB_DATA.md)), as a cross-check | |
| The app's output on the same particles | A training set for the v3 model (part 5), split by sample |
| New labels from review (part 6) | A fixed gold test set (part 10) |
| | Agreement reports: detection, size error, colour and shape confusion |

The lab's data stays in Drive and is not committed here: it's the lab's, and the terms are open question 9. Scripts read it from a local folder.

## What exists

| File | Does |
|---|---|
| `lab_photo_check.py` | Matches the app's particles to the lab's spreadsheet rows (.xlsx or .csv) on their "Rows A–H" ruler photos, and reports agreement for size, colour and shape. White or black backgrounds; any number of plate rows. Saves each matched particle's colour pixels for fitting the colour rules |
| `ruler.py` | Reads the scale from a ruler with no help (millimetre edge, told apart from an inch edge), and masks the ruler out. `--check-image` writes a picture to check it by eye |
| `run_lab_photos.py` + `lab_photos.csv` | Runs the check on a list of photos and writes one summary table |
| `test_ruler.py` | Tests the ruler reader on drawn rulers with a known scale |
| `legacy/` | The lab's old 12 × 24 checkerboard with an empty-board photo (`run.py`, `board.py`, `segment.py`, tests): not an app input, kept to compare with the lab's ImageJ results |
| `compare_imagej.py` | Compares with the lab's ImageJ results on the fragment_area sample (median area +0.5%, Feret −0.2%; `results/fragment_area_sample/`) |
| `perimeter_study.py` | Perimeter methods on shapes with a known answer (`reports/perimeter_study.txt`) |

## To build

- [ ] **Settle the scale gap with the lab:** measure one particle with calipers. The lab's older sizes vary by session (+12% to −2% against the ruler), so they can't be ground truth as they are.
- [x] **Run `lab_photo_check.py` on more photos** and collect the matches into one table: 20 photos from EX_01, EX_02, OC_03, OC_05–07 and an LFB (see `reports/lab_photos.md`).
- [ ] SF_04 photos: their sheet (SF_04) isn't in Drive's ParticleCount folder.
- [ ] **Re-photograph the lab's labelled particles on the printed sheets** (all three backgrounds), with a well-to-box list, so their hand labels carry over. Then measure a few with calipers as the size reference.
- [ ] **Compare box by box** on those sheet photos: size against the lab's sizes and calipers, colour and morphology against the lab's labels. Count missed and extra detections from the well-to-box list. Outlines are only looked at where a size or shape came out wrong; no hand-drawn outlines.
- [ ] **Set the flag thresholds** from the results: which `size_uncertainty`, contrast and solidity values go with wrong results. In use, the same checks run with these thresholds and send flagged particles to review first.
- [ ] **Build the labelled set** from those sheet photos: crops + the lab's shape and colour labels, split into train / validation / test **by sample**.
- [ ] **A second person labels 20%** of particles independently, to get the agreement ceiling (Cohen's kappa for classes).
- [ ] **New labels for missing classes** on the sheets: film, foam, clear particles.
- [ ] **Agree the pass mark** (open question 6) after seeing the agreement per class.
- [ ] **The validation report:**
  - detection recall and precision
  - size error in mm
  - confusion matrices for colour and shape
  - how many particles need review
  - time saved versus the manual workflow
  - a test on a second setup or lab

## Watch for

Don't tune on the test set. A model only proven on the pilot setup isn't a standard method.
