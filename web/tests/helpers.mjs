// Test helpers: load the pinned OpenCV.js in Node, and read the greyscale PNG fixtures.
import { createHash } from "node:crypto";
import { existsSync, readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { inflateSync } from "node:zlib";
import { OPENCV, whenReady } from "../src/opencv.js";

const vendorFile = new URL(`../${OPENCV.vendorPath}`, import.meta.url);

/** The pinned OpenCV.js, or null when it hasn't been fetched (node web/scripts/fetch_opencv.mjs). */
export async function loadOpenCVNode() {
  if (!existsSync(vendorFile)) return null;
  const sha = createHash("sha256").update(readFileSync(vendorFile)).digest("hex");
  if (sha !== OPENCV.sha256) throw new Error(`${OPENCV.vendorPath} has sha256 ${sha}, expected ${OPENCV.sha256}`);
  return whenReady(createRequire(import.meta.url)(vendorFile.pathname));
}

/** 8-bit greyscale, non-interlaced PNG -> {width, height, data}. */
export function readGrayPng(path) {
  const buf = readFileSync(path);
  let width, height;
  const idat = [];
  for (let off = 8; off < buf.length;) {
    const len = buf.readUInt32BE(off);
    const type = buf.toString("latin1", off + 4, off + 8);
    const body = buf.subarray(off + 8, off + 8 + len);
    if (type === "IHDR") {
      [width, height] = [body.readUInt32BE(0), body.readUInt32BE(4)];
      if (body[8] !== 8 || body[9] !== 0 || body[12] !== 0) throw new Error(`${path}: not 8-bit greyscale`);
    } else if (type === "IDAT") idat.push(body);
    off += 12 + len;
  }
  const raw = inflateSync(Buffer.concat(idat));
  const data = new Uint8Array(width * height);
  for (let y = 0; y < height; y++) {
    const filter = raw[y * (width + 1)];
    const src = raw.subarray(y * (width + 1) + 1, (y + 1) * (width + 1));
    const row = data.subarray(y * width, (y + 1) * width);
    const up = y ? data.subarray((y - 1) * width, y * width) : new Uint8Array(width);
    for (let x = 0; x < width; x++) {
      const a = x ? row[x - 1] : 0;
      const b = up[x];
      const c = x ? up[x - 1] : 0;
      let p;
      if (filter === 0) p = 0;
      else if (filter === 1) p = a;
      else if (filter === 2) p = b;
      else if (filter === 3) p = (a + b) >> 1;
      else {
        const pa = Math.abs(b - c), pb = Math.abs(a - c), pc = Math.abs(a + b - 2 * c);
        p = pa <= pb && pa <= pc ? a : pb <= pc ? b : c;
      }
      row[x] = (src[x] + p) & 255;
    }
  }
  return { width, height, data };
}
