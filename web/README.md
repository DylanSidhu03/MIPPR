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

Built so far (part 1, the marker stage):
- `src/capture/sheet.js`: the sheet layout (papers, box grid and labels, marker IDs and corners, 100 mm line, patches, background types), `detectMarkers`, `findSheet` (layout from the marker IDs, px per mm, homography) and `rectifySheet`. Pure ES module: no DOM, and OpenCV.js is passed in as `cv`.
- `src/opencv.js`: the pinned OpenCV.js build and `loadOpenCV()`.

Everything else in `src/` is still a stub (each function throws "not implemented"), including `rectifyGrid` (the grid-crossing refinement) and `whiteBalance`.

## Technical choices

- **Plain ES modules, no build step** (approved), so Cloudflare Pages serves the folder as is.
- **OpenCV.js 4.10.0**, the official `docs.opencv.org/4.10.0/opencv.js` build as redistributed in the npm package `@techstark/opencv-js@4.10.0-release.1` (the package says it is the docs.opencv.org file plus a one-line UMD patch; docs.opencv.org was not reachable from the dev container to compare hashes). The browser loads it from jsDelivr with a subresource-integrity hash; the version, URLs and hashes are in `src/opencv.js`. It is a UMD script, so it is loaded with a script tag, not `import`.
- **Parity tests** against the Python reference, with fixtures made by the Python code and committed.

### ArUco in OpenCV.js

The official 4.10.0 build includes ArUco (checked November 12, 2026): `cv.getPredefinedDictionary(cv.DICT_4X4_50)`, `cv.aruco_DetectorParameters`, `cv.aruco_RefineParameters` and `cv.aruco_ArucoDetector(...).detectMarkers(img, corners, ids, rejected)`. Note the `aruco_` prefixes: there is no `cv.ArucoDetector`. On the synthetic photos it finds the same markers as Python's `cv2.aruco` (OpenCV 5.0.0) with identical corners (0 px difference), in Node and in Chromium. 4.12.0 behaves the same; 5.0.0 also works but returns `ids` as 1 x N, which `detectMarkers` handles.

Missing from the 4.10.0 build, and needed later: `cornerSubPix` (checkerboard crossing refinement in `sheet.py`), `findChessboardCorners` (legacy board), `boxPoints` and `getTextSize`. These need small JS versions, or a custom build.

## Tests

```bash
node web/scripts/fetch_opencv.mjs   # once: downloads the pinned opencv.js (10 MB) to web/vendor/ and checks its sha256
node --test web/tests/
```

- `sheet_layout.test.mjs`: the JS layout against `fixtures/layouts.json` (every background and paper, plus non-default box sizes), within 1e-6 mm.
- `sheet_markers.test.mjs`: marker corners, layout, px per mm, homography and rectified pixels against `fixtures/markers.json`, on two synthetic photos, each also with one marker covered. These tests are skipped if `web/vendor/` has not been fetched.

To regenerate the fixtures after changing `pipeline/mippr/capture/sheet.py` (from the repo root):

```bash
.venv/bin/python web/tests/dump_python_layout.py
.venv/bin/python web/tests/dump_python_markers.py
```

Serve the repo root (`python -m http.server`) and open `/web/` to try the page; the background links point to `../backgrounds/`.

## To build

- [ ] Sketch the screens: print background, upload, sample details, run with progress, review, export
- [x] Serve the printable PDFs from `backgrounds/` (links on `index.html`)
- [ ] Port parts 1–5 module by module (part 1 marker stage done: layout, marker detection, homography, sheet rectification), each passing the parity tests. The marching-squares outline and the skeleton step need their own code (not in OpenCV.js).
- [ ] Batch processing in the browser on the user's machine, with a clear message for each failed photo (quality check, part 1)
- [ ] Scale entry for photos without the printed sheet (a ruler), with guidance
- [ ] Export the files above; a PDF or HTML summary
- [ ] Python batch command for the lab (`pipeline/mippr/batch.py`, planned)
- [ ] Cloudflare Pages deployment from the GitHub repo; upload size limits
- [ ] License, contribution notes, automated tests on each push
- [ ] Methods page (class definitions, calibration, accuracy, known limits) and a 1.0 release with a changelog
- [ ] Pilot with two or three outside users

## Decision point before building

Go when validation (part 7) meets its targets and someone other than the team has run the batch tool. A hosting and upkeep plan is also needed (who maintains it after the practicum, open question 7).
