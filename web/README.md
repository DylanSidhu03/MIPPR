# Part 8: The app (browser, hosted on Cloudflare Pages)

The website people use: print a background, upload photos, get results, review them and export. It also covers the outputs (CSV, overlay, summary) and the release.

**Method:** software. All image processing runs **in the user's browser** (OpenCV.js, and ONNX Runtime Web for the v3 model). Cloudflare Pages only serves the files, and there is no processing server (Drive spec: free to run).

## In → Out

| In | Out |
|---|---|
| Photos and sample details typed by the user | `particles.csv`, `summary.csv`, `overlay.png`, `run.json`, `NOTE.txt`, exactly as [docs/OUTPUT_CSV.md](../docs/OUTPUT_CSV.md) |
| | Reviewed rows saved to Supabase (part 9) |

## Layout

`src/` mirrors the Python reference in `pipeline/mippr/`, one folder per part, so each piece can be ported and checked on its own:

| Folder | Part | Python reference |
|---|---|---|
| `src/capture/` | 1 Capture and calibration | `capture/` |
| `src/segmentation/` | 2 Segmentation | `segmentation/` |
| `src/measurement/` | 3 Measurement | `measurement/` |
| `src/color/` | 4 Colour | `color/` |
| `src/morphology/` | 5 Morphology (rules, and the ONNX model) | `morphology/` |
| `src/review/` | 6 Review screen | `review/` |
| `src/storage/` | 9 Supabase client | `database/` |
| `src/export/` | 8 CSV and summary | `export.py` |
| `src/app.js`, `index.html` | 8 Screens and flow | `cli.py` |

## What's built

**Parts 1–5 run in the browser, end to end** (`src/pipeline.js` `runGrid`, the twin of Python's `cli.run_grid`; `src/app.js` `processPhoto` takes a canvas image). Every module takes OpenCV.js as `cv`, with no DOM, so it runs in Node for tests.

| Module | Does | Parity with Python |
|---|---|---|
| `capture/sheet.js`, `subpix.js` | Layout, markers, homography, grid-crossing refinement, flattening, white balance | crossings within 0.002 px on five synthetic photos; flattened grid within 1 grey level |
| `capture/quality.js` | Photo quality check (same codes, messages, limits) | identical codes on 37 degraded photos |
| `capture/printer.js` | Printer scale from the paper's edges, through a radial lens model (`printer_scale` in calibration.py) | scale within 5 parts in 10,000 and edges within 0.1 mm on five photos, incl. 97% and A4-on-Letter prints |
| `segmentation/edges.js`, `grid.js` | Per-box background, line bridging, hysteresis, half-maximum edges | labels pixel for pixel on all three backgrounds |
| `measurement/*.js` | Sizes and shape as ImageJ computes them (Feret, traced perimeter, fitted ellipse), sub-pixel perimeter, colour statistics, fiber length, opacity, size range | floating-point precision on every field |
| `color/rules.js`, `morphology/rules.js`, `export/csv.js` | Colour and shape rules, rows, summary, CSV | rows exact; CSV byte for byte |
| `pipeline.js` | The whole photo → rows run | text and flags identical; numbers within about a pixel (below) |

**The one known difference.** On the same photo, OpenCV.js 4.10's flattening differs from Python's OpenCV 5 by up to one grey level on a few pixels, which can flip a pixel right at a particle's edge. So, end to end, text, labels and flags are identical, but numbers can differ slightly: for 2–9 mm particles, area within one pixel (≤ 0.3%) and length exact; a 0.6 mm particle (about 60 px in area) moved 6% in area. Rule confidences, from a steep curve, moved up to about 0.04. Each module on identical inputs matches exactly; this comes only from the flattening's resampling, and could be removed by writing the remap in JS like `subpix.js`'s warp, if exact agreement is wanted.

**The app (`index.html`, `style.css`, `src/app.js`)**: print a background; type the sample details and choose photos; measure (in the browser, a message per photo, refused photos say why); check the results on the review screen (`src/review/screen.js`: the flattened grid with outlines coloured by status, click or keys to select, confirm, reject, relabel, tar-like and bundle tags, in review order, with the rules of `src/review/corrections.js`); download particles.csv, summary.csv, run.json and NOTE.txt. The reviewer's name and role are remembered in the browser. `?opencv=local` loads OpenCV.js from `vendor/` instead of the CDN.

`node web/scripts/smoke_ui.mjs` runs the app in Chromium (Playwright): measures two sheet photos, refuses one without a sheet, reviews with keys and a click, and checks the downloaded CSVs. CI runs it too.

Still stubs: `storage/supabase.js` (part 9) and `morphology/model.js` (v3). Not built yet: redrawing an outline on the screen (the rules and re-measuring work), the overlay image download, and a Web Worker for large batches.

Small tidy-up left: `measurement/_edges.js` repeats `edgeLevel` and `fillHoles` from `segmentation/edges.js` (they take plain arrays rather than Mats); merge them after checking the float32 median rounding is the same.

## Technical choices

- **Plain ES modules, no build step** (approved), so Cloudflare Pages serves the folder as is.
- **OpenCV.js 4.10.0**, the official `docs.opencv.org/4.10.0/opencv.js` build as redistributed in the npm package `@techstark/opencv-js@4.10.0-release.1` (the package says it is the docs.opencv.org file plus a one-line UMD patch; docs.opencv.org was not reachable from the dev container to compare hashes). The browser loads it from jsDelivr with a subresource-integrity hash; the version, URLs and hashes are in `src/opencv.js`. It is a UMD script, so it is loaded with a script tag, not `import`.
- **Parity tests** against the Python reference, with fixtures made by the Python code and committed.

### ArUco in OpenCV.js

The official 4.10.0 build includes ArUco (checked November 12, 2026): `cv.getPredefinedDictionary(cv.DICT_4X4_50)`, `cv.aruco_DetectorParameters`, `cv.aruco_RefineParameters` and `cv.aruco_ArucoDetector(...).detectMarkers(img, corners, ids, rejected)`. Note the `aruco_` prefixes: there is no `cv.ArucoDetector`. On the synthetic photos it finds the same markers as Python's `cv2.aruco` (OpenCV 5.0.0) with identical corners (0 px difference), in Node and in Chromium. 4.12.0 behaves the same; 5.0.0 also works but returns `ids` as 1 x N, which `detectMarkers` handles.

Missing from the 4.10.0 build, and needed later: `cornerSubPix` (checkerboard crossing refinement in `sheet.py`), `boxPoints` and `getTextSize`. These need small JS versions, or a custom build. (`findChessboardCorners` is missing too, but isn't needed: the app only takes the printed sheets, found by their markers.)

## Tests

```bash
node web/scripts/fetch_opencv.mjs   # once: downloads the pinned opencv.js (10 MB) to web/vendor/ and checks its sha256
node --test "web/tests/*.test.mjs"
```

- `sheet_layout.test.mjs`: the JS layout against `fixtures/layouts.json` (every background and paper, plus non-default box sizes), within 1e-6 mm.
- `sheet_markers.test.mjs`: marker corners, layout, px per mm, homography and rectified pixels against `fixtures/markers.json`, on two synthetic photos, each also with one marker covered. These tests are skipped if `web/vendor/` has not been fetched.

To regenerate the fixtures after changing `pipeline/mippr/capture/sheet.py` (from the repo root):

```bash
.venv/bin/python web/tests/dump_python_layout.py
.venv/bin/python web/tests/dump_python_markers.py
.venv/bin/python web/tests/dump_python_quality.py
.venv/bin/python web/tests/dump_python_printer.py
```

Serve the repo root (`python -m http.server`) and open `/web/` to try the page; the background links point to `../backgrounds/`.

## To build

- [x] Screens: print background, upload, sample details, run with progress, review, export
- [x] Serve the printable PDFs from `backgrounds/` (links on `index.html`)
- [x] Port parts 1–5 module by module, each passing the parity tests, and join them (`pipeline.js`), checked end to end against Python on all three backgrounds
- [x] Draw the overlay (outlines and box labels) on a canvas for the results and review screens
- [x] Batch processing in the browser on the user's machine, with a clear message for each failed photo (quality check, part 1)
- [ ] Run the processing in a Web Worker so the page stays responsive
- [x] Photo guidance: print at actual size, whole sheet and all four markers in frame, even light, no flash. A photo without the markers is refused with that message (the app only takes the three printed backgrounds).
- [x] Export particles.csv, summary.csv, run.json, NOTE.txt
- [ ] Overlay image download; a PDF or HTML summary
- [ ] Redraw an outline on the review screen
- [x] Python batch command for the lab (`python -m mippr.cli batch`)
- [ ] Cloudflare Pages deployment from the GitHub repo; upload size limits
- [x] Automated tests on each push
- [ ] License and contribution notes
- [ ] Methods page (class definitions, calibration, accuracy, known limits) and a 1.0 release with a changelog
- [ ] Pilot with two or three outside users

## Decision point before building

Go when validation (part 7) meets its targets and someone other than the team has run the batch tool. A hosting and upkeep plan is also needed (who maintains it after the practicum, open question 7).
