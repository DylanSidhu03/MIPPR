// Download the pinned OpenCV.js (see web/src/opencv.js) into web/vendor/ and check its sha256.
// Usage: node web/scripts/fetch_opencv.mjs
import { createHash } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { gunzipSync } from "node:zlib";
import { OPENCV } from "../src/opencv.js";

const web = join(dirname(fileURLToPath(import.meta.url)), "..");
const out = join(web, OPENCV.vendorPath);
const sha256 = (buf) => createHash("sha256").update(buf).digest("hex");

if (existsSync(out) && sha256(readFileSync(out)) === OPENCV.sha256) {
  console.log(`${OPENCV.vendorPath} is already there (OpenCV.js ${OPENCV.version}).`);
  process.exit(0);
}

/** One file from a .tar archive (ustar headers, 512-byte blocks). */
function untar(tar, wanted) {
  for (let off = 0; off + 512 <= tar.length;) {
    const name = tar.toString("latin1", off, off + 100).replace(/\0.*$/s, "");
    if (!name) break;
    const size = parseInt(tar.toString("latin1", off + 124, off + 136).trim(), 8);
    if (name === wanted) return tar.subarray(off + 512, off + 512 + size);
    off += 512 + Math.ceil(size / 512) * 512;
  }
  throw new Error(`${wanted} is not in the archive`);
}

const res = await fetch(OPENCV.tarball);
if (!res.ok) throw new Error(`${OPENCV.tarball}: HTTP ${res.status}`);
const js = untar(gunzipSync(Buffer.from(await res.arrayBuffer())), "package/dist/opencv.js");
const got = sha256(js);
if (got !== OPENCV.sha256) throw new Error(`sha256 mismatch: got ${got}, expected ${OPENCV.sha256}`);
mkdirSync(dirname(out), { recursive: true });
writeFileSync(out, js);
console.log(`Wrote ${OPENCV.vendorPath} (OpenCV.js ${OPENCV.version}, ${(js.length / 1e6).toFixed(1)} MB, sha256 ok).`);
