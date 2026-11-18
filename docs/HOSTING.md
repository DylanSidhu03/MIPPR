# Hosting the app on Cloudflare Pages

The app is a static site: every photo is processed in the visitor's browser, so Cloudflare only serves files. It stays on the project owner's GitHub and Cloudflare accounts (decided November 18, 2026), and OpenCV.js is served with the site rather than from a CDN.

## One-time setup (Cloudflare dashboard)

1. Cloudflare dashboard → **Workers & Pages** → **Create** → **Pages** → **Connect to Git**, and pick this repository.
2. Build settings:

   | Setting | Value |
   |---|---|
   | Production branch | the branch to publish (e.g. `main`) |
   | Framework preset | None |
   | Build command | `node scripts/build_site.mjs` |
   | Build output directory | `dist` |
   | Environment variable | `NODE_VERSION` = `22` |

3. Save and deploy. Every push to the production branch publishes; other branches get preview URLs.

No secrets or environment variables are needed: the site has no backend yet (Supabase comes with part 9).

## What the build does

`scripts/build_site.mjs` makes `dist/`:
- `index.html`, `style.css` and `src/`: the app, as in `web/`, with the background links pointing at `backgrounds/`
- `vendor/opencv-4.10.0.js`: downloaded from the pinned npm package and checked against its sha256 (`web/scripts/fetch_opencv.mjs`); 10.4 MB, under Cloudflare's 25 MiB per-file limit
- `backgrounds/*.pdf`: the printable sheets, plain and with colour patches
- `_headers`: a strict Content-Security-Policy (only the site's own files; `'unsafe-eval'` and `'wasm-unsafe-eval'`, which OpenCV.js needs: its glue code builds functions from strings and it compiles WebAssembly), `nosniff`, no referrer, and caching (OpenCV.js a year, since its file name carries its version)

Try the built site locally: `node scripts/build_site.mjs && SMOKE_ROOT=dist node web/scripts/smoke_ui.mjs` runs the whole app in a browser with those headers applied (CI does the same).

## Limits

- Photos up to 60 MB and 60 megapixels (`web/src/limits.js`); larger ones are refused with a message, because they would exhaust the browser's memory. Phone photos are 12–50 MP.
- Cloudflare Pages' free plan: 500 builds a month, 20,000 files and 25 MiB per file. The site is about 11 MB in 70 files.
- How many photos one batch can take depends on the visitor's computer; each photo is processed and released in turn.
