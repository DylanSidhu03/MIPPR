// Build the static site for Cloudflare Pages into dist/ (docs/HOSTING.md).
//
//   node scripts/build_site.mjs        # Cloudflare Pages: build command; output directory: dist
//
// dist/ holds the app (web/index.html, style.css, src/), OpenCV.js (fetched and sha256-checked by
// web/scripts/fetch_opencv.mjs, served with the site as decided), the printable backgrounds, and
// Cloudflare's _headers (security and caching). Nothing is processed on a server: the site is static.
import { execFileSync } from "node:child_process";
import { copyFileSync, cpSync, existsSync, mkdirSync, readdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { OPENCV } from "../web/src/opencv.js";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const web = join(root, "web");
const dist = join(root, process.argv[2] ?? "dist");

execFileSync(process.execPath, [join(web, "scripts", "fetch_opencv.mjs")], { stdio: "inherit" });
rmSync(dist, { recursive: true, force: true });
mkdirSync(dist, { recursive: true });

// The page: the backgrounds move from ../backgrounds/ (repo layout) to backgrounds/ (site root).
const html = readFileSync(join(web, "index.html"), "utf8").replaceAll('href="../backgrounds/', 'href="backgrounds/');
writeFileSync(join(dist, "index.html"), html);
copyFileSync(join(web, "style.css"), join(dist, "style.css"));
cpSync(join(web, "src"), join(dist, "src"), { recursive: true });
mkdirSync(join(dist, "vendor"));
copyFileSync(join(web, OPENCV.vendorPath), join(dist, OPENCV.vendorPath));
mkdirSync(join(dist, "backgrounds"));
for (const f of readdirSync(join(root, "backgrounds"))) {
  if (f.endsWith(".pdf")) copyFileSync(join(root, "backgrounds", f), join(dist, "backgrounds", f));
}

// Cloudflare Pages headers. Scripts only from the site itself. OpenCV.js needs 'unsafe-eval' (its embind
// glue builds functions from strings with new Function) and 'wasm-unsafe-eval' (it compiles WebAssembly,
// first fetching it from a data: URL, hence connect-src data:);
// found by running the built site under this policy. blob: covers the downloads the app makes. OpenCV.js
// and the PDFs never change under the same name, so they may be cached for a long time; the app's own files
// are revalidated.
writeFileSync(join(dist, "_headers"), `/*
  Content-Security-Policy: default-src 'self'; script-src 'self' 'unsafe-eval' 'wasm-unsafe-eval'; worker-src 'self'; img-src 'self' data: blob:; style-src 'self'; connect-src 'self' data:; object-src 'none'; base-uri 'self'; form-action 'none'; frame-ancestors 'none'
  X-Content-Type-Options: nosniff
  Referrer-Policy: no-referrer
  Permissions-Policy: camera=(), microphone=(), geolocation=()
  Cache-Control: no-cache

/vendor/*
  Cache-Control: public, max-age=31536000, immutable

/backgrounds/*
  Cache-Control: public, max-age=86400
`);

const size = (dir) => readdirSync(dir, { withFileTypes: true })
  .reduce((s, e) => s + (e.isDirectory() ? size(join(dir, e.name)) : readFileSync(join(dir, e.name)).length), 0);
if (!existsSync(join(dist, OPENCV.vendorPath))) throw new Error("OpenCV.js is missing from dist/");
console.log(`Built ${dist} (${(size(dist) / 1e6).toFixed(1)} MB). Cloudflare Pages: output directory "dist".`);
