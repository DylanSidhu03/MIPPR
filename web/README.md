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

Everything in `src/` is a stub today (each function throws "not implemented").

## Proposed technical choices (to confirm)

- **Plain ES modules, no build step**, so Cloudflare Pages serves the folder as is. This is the easiest to maintain and free. Add a bundler only if OpenCV.js or ONNX loading needs one.
- **OpenCV.js** from a pinned version. Check first that its build includes the ArUco module; if not, use a custom build or a JS marker library.
- **Parity tests:** run the synthetic photo and the fragment_area sample through both the Python pipeline and the browser code, and require the same particles and measurements within a small tolerance. This is how each port step is checked.

## To build

- [ ] Sketch the screens: print background, upload, sample details, run with progress, review, export
- [ ] Serve the printable PDFs from `backgrounds/`
- [ ] Port parts 1–5 module by module, each passing the parity tests. The marching-squares outline and the skeleton step need their own code (not in OpenCV.js).
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
