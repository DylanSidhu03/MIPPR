// Small helpers shared by the measurement modules: plain pixel grids, crops, and the OpenCV.js
// morphology and contour calls they need. A grid is {width, height, channels, data} in row-major order.

/** A cv.Mat (or an existing grid) as a plain grid. Mat data is copied: views into the WASM heap go stale when it grows. */
export function plain(m) {
  if (m == null) return null;
  if (typeof m.type !== "function") return { channels: 1, ...m };
  const view = ["data", "data8S", "data16U", "data16S", "data32S", "data32F", "data64F"][m.type() % 8];
  const data = m[view];
  return { width: m.cols, height: m.rows, channels: m.channels(), data: data.slice() };
}

/** Copy of the window [x0, x1) x [y0, y1), keeping the typed-array type. */
export function crop(g, x0, y0, x1, y1) {
  const c = g.channels || 1;
  const w = x1 - x0, h = y1 - y0;
  const data = new g.data.constructor(w * h * c);
  for (let y = 0; y < h; y++) data.set(g.data.subarray(((y0 + y) * g.width + x0) * c, ((y0 + y) * g.width + x1) * c), y * w * c);
  return { width: w, height: h, channels: c, data };
}

export function maskMat(cv, mask) {
  const mat = new cv.Mat(mask.height, mask.width, cv.CV_8UC1);
  mat.data.set(mask.data);
  return mat;
}

/** Grid -> cv.Mat of the matching type (8-bit, 32-bit float or 64-bit float). */
export function toMat(cv, g) {
  const c = g.channels || 1;
  const depth = g.data instanceof Float32Array ? cv.CV_32F : g.data instanceof Float64Array ? cv.CV_64F : cv.CV_8U;
  const mat = new cv.Mat(g.height, g.width, depth + (c - 1) * 8);
  const view = depth === cv.CV_32F ? mat.data32F : depth === cv.CV_64F ? mat.data64F : mat.data;
  view.set(g.data);
  return mat;
}

/** cv.erode / cv.dilate of a 0/1 mask with a size x size rectangle or ellipse, default borders as in cv2. */
export function morph(cv, op, mask, size, shape = "rect") {
  const src = maskMat(cv, mask);
  const kernel = cv.getStructuringElement(shape === "ellipse" ? cv.MORPH_ELLIPSE : cv.MORPH_RECT, new cv.Size(size, size));
  const dst = new cv.Mat();
  if (op === "erode") cv.erode(src, dst, kernel);
  else cv.dilate(src, dst, kernel);
  const out = { width: mask.width, height: mask.height, channels: 1, data: Uint8Array.from(dst.data) };
  src.delete();
  kernel.delete();
  dst.delete();
  return out;
}

export function count(mask) {
  let n = 0;
  for (const v of mask.data) if (v) n++;
  return n;
}

/** External contours (cv.findContours, RETR_EXTERNAL, CHAIN_APPROX_NONE) as arrays of [x, y], shifted by (dx, dy). */
export function externalContours(cv, mask, dx = 0, dy = 0) {
  const src = maskMat(cv, mask);
  const contours = new cv.MatVector();
  const hierarchy = new cv.Mat();
  cv.findContours(src, contours, hierarchy, cv.RETR_EXTERNAL, cv.CHAIN_APPROX_NONE);
  const out = [];
  for (let i = 0; i < contours.size(); i++) {
    const c = contours.get(i);
    const pts = [];
    for (let k = 0; k < c.data32S.length; k += 2) pts.push([c.data32S[k] + dx, c.data32S[k + 1] + dy]);
    out.push(pts);
    c.delete();
  }
  src.delete();
  contours.delete();
  hierarchy.delete();
  return out;
}
