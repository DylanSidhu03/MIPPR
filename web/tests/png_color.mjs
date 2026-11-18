// Test helper: read 8-bit greyscale, RGB or RGBA PNG fixtures (non-interlaced), and turn them into OpenCV.js Mats.
import { readFileSync } from "node:fs";
import { inflateSync } from "node:zlib";

const CHANNELS = { 0: 1, 2: 3, 6: 4 };

/** PNG -> {width, height, channels, data} with channels interleaved as stored (grey, RGB or RGBA). */
export function readPng(path) {
  const buf = readFileSync(path);
  let width, height, channels;
  const idat = [];
  for (let off = 8; off < buf.length;) {
    const len = buf.readUInt32BE(off);
    const type = buf.toString("latin1", off + 4, off + 8);
    const body = buf.subarray(off + 8, off + 8 + len);
    if (type === "IHDR") {
      [width, height] = [body.readUInt32BE(0), body.readUInt32BE(4)];
      channels = CHANNELS[body[9]];
      if (body[8] !== 8 || !channels || body[12] !== 0) throw new Error(`${path}: not an 8-bit grey/RGB/RGBA PNG`);
    } else if (type === "IDAT") idat.push(body);
    off += 12 + len;
  }
  const raw = inflateSync(Buffer.concat(idat));
  const stride = width * channels;
  const data = new Uint8Array(stride * height);
  for (let y = 0; y < height; y++) {
    const filter = raw[y * (stride + 1)];
    const src = raw.subarray(y * (stride + 1) + 1, (y + 1) * (stride + 1));
    const row = data.subarray(y * stride, (y + 1) * stride);
    const up = y ? data.subarray((y - 1) * stride, y * stride) : new Uint8Array(stride);
    for (let x = 0; x < stride; x++) {
      const a = x >= channels ? row[x - channels] : 0;
      const b = up[x];
      const c = x >= channels ? up[x - channels] : 0;
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
  return { width, height, channels, data };
}

/** PNG -> Mat as cv2.imread(path, IMREAD_UNCHANGED) gives it: greyscale, or colour in BGR(A) order. */
export function readPngMat(cv, path) {
  const { width, height, channels, data } = readPng(path);
  const mat = new cv.Mat(height, width, [0, cv.CV_8UC1, 0, cv.CV_8UC3, cv.CV_8UC4][channels]);
  if (channels >= 3) {
    for (let i = 0; i < data.length; i += channels) [data[i], data[i + 2]] = [data[i + 2], data[i]];
  }
  mat.data.set(data);
  return mat;
}
