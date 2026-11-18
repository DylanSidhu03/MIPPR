// Part 1: browser port of pipeline/mippr/capture/sheet.py.
// The layout is plain geometry (no DOM, no OpenCV). Detection and rectification take the OpenCV.js
// module as their first argument (see ../opencv.js), so the same code runs in the browser and in Node.
// Parity with the Python reference is checked by web/tests/.
import { cornerSubPix, warpPerspectiveLinear } from "./subpix.js";

export const BACKGROUNDS = Object.freeze(["white_grid", "black_grid", "checkerboard"]);
export const PAPERS = Object.freeze({ letter: Object.freeze([215.9, 279.4]), a4: Object.freeze([210.0, 297.0]) });
export const ARUCO_DICT = "DICT_4X4_50";
export const LAYOUT_VERSION = 1;

const LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ";

const DEFAULTS = Object.freeze({
  background: "white_grid",
  paper: "letter",
  boxMm: 12.0, // "around 10 mm or more"; particles in scope are 0.5-5 mm
  lineMm: 0.5, // "Standard" design, chosen November 5, 2026
  marginMm: 8.0, // unprinted edge most printers need
  markerMm: 18.0,
  gapMm: 8.0, // between the markers' inner edge and the grid, room for labels
  boxLabels: true, // also print each box's label (e.g. B4) small in its top-left corner
  labelZoneMm: Object.freeze([6.5, 3.2]), // top-left corner kept for the label
  colorPatches: false, // also print six coloured patches beside the white and grey ones
});
export const COLOR_PATCH_ID_OFFSET = 24; // the coloured-patch sheets use marker IDs 24-47
// Printer primaries and secondaries (RGB 0-1): a record and a consistency check between photos of one
// printout, not a colour standard, since printers render them differently. No result uses them.
export const COLOR_PATCHES = Object.freeze({ red: [1, 0, 0], yellow: [1, 1, 0], green: [0, 1, 0],
  cyan: [0, 1, 1], blue: [0, 0, 1], magenta: [1, 0, 1] });

/** Python's float floor division (`a // b`), which can differ from Math.floor(a / b) near whole numbers. */
function floorDiv(a, b) {
  let mod = a % b;
  let div = (a - mod) / b;
  if (mod && (b < 0) !== (mod < 0)) {
    mod += b;
    div -= 1;
  }
  if (!div) return 0;
  const f = Math.floor(div);
  return div - f > 0.5 ? f + 1 : f;
}

/** Python's round(x, ndigits) for the values used here: half to even. */
export function pyRound(x, ndigits = 0) {
  const k = 10 ** ndigits;
  const v = x * k;
  const r = Math.round(v);
  return (Math.abs(v % 1) === 0.5 && r % 2 ? r - 1 : r) / k;
}

/** Geometry of one printable sheet, in mm from the top-left of the paper. */
export class Layout {
  constructor(options = {}) {
    const o = { ...DEFAULTS, ...options };
    if (!BACKGROUNDS.includes(o.background)) throw new Error(`background must be one of ${BACKGROUNDS.join(", ")}`);
    if (!(o.paper in PAPERS)) throw new Error(`paper must be one of ${Object.keys(PAPERS).join(", ")}`);
    for (const k of Object.keys(DEFAULTS)) this[k] = o[k];
    this.labelZoneMm = Object.freeze([...o.labelZoneMm]);
    Object.freeze(this);
  }

  get sizeMm() {
    return PAPERS[this.paper];
  }

  get cols() {
    const w = this.sizeMm[0] - 2 * (this.marginMm + this.markerMm + this.gapMm);
    return floorDiv(w, this.boxMm);
  }

  get rows() {
    const h = this.sizeMm[1] - 2 * (this.marginMm + this.markerMm + this.gapMm);
    return Math.min(floorDiv(h, this.boxMm), 26);
  }

  /** Top-left corner of the grid, centred on the sheet. */
  get gridOriginMm() {
    const [w, h] = this.sizeMm;
    return [(w - this.cols * this.boxMm) / 2, (h - this.rows * this.boxMm) / 2];
  }

  get gridSizeMm() {
    return [this.cols * this.boxMm, this.rows * this.boxMm];
  }

  /** IDs for the top-left, top-right, bottom-right and bottom-left markers. */
  markerIds() {
    const papers = Object.keys(PAPERS);
    const base = 4 * (BACKGROUNDS.indexOf(this.background) * papers.length + papers.indexOf(this.paper)) +
      (this.colorPatches ? COLOR_PATCH_ID_OFFSET : 0);
    return [base, base + 1, base + 2, base + 3];
  }

  /** {marker id: 4 corners [x, y] (TL, TR, BR, BL as OpenCV reports them)} in sheet mm. */
  markerCornersMm() {
    const [w, h] = this.sizeMm;
    const m = this.marginMm;
    const s = this.markerMm;
    const origins = [[m, m], [w - m - s, m], [w - m - s, h - m - s], [m, h - m - s]];
    const out = {};
    this.markerIds().forEach((id, i) => {
      const [x, y] = origins[i];
      out[id] = [[x, y], [x + s, y], [x + s, y + s], [x, y + s]];
    });
    return out;
  }

  boxLabel(row, col) {
    return `${LETTERS[row]}${col + 1}`;
  }

  /** End points of the printed 100 mm check line, in the bottom margin. */
  scaleLineMm() {
    const [w, h] = this.sizeMm;
    const y = h - this.marginMm - this.markerMm / 2;
    return [[w / 2 - 50, y], [w / 2 + 50, y]];
  }

  /** {name: [x, y, w, h, grey level 0-255]} white-balance patches in the top margin. */
  patchesMm() {
    const w = this.sizeMm[0];
    const y = this.marginMm + 2;
    return { white: [w / 2 - 26, y, 24, 12, 255], grey: [w / 2 + 2, y, 24, 12, 128] };
  }

  /** {name: [x, y, w, h, [r, g, b] 0-1]} coloured patches either side of the white and grey ones (empty if none). */
  colorPatchesMm() {
    if (!this.colorPatches) return {};
    const w = this.sizeMm[0];
    const y = this.marginMm + 2;
    const xs = [w / 2 - 70, w / 2 - 56, w / 2 - 42, w / 2 + 30, w / 2 + 44, w / 2 + 58]; // 12 mm squares, 2 mm apart
    return Object.fromEntries(Object.entries(COLOR_PATCHES).map(([name, rgb], i) => [name, [xs[i], y, 12, 12, [...rgb]]]));
  }

  /** File-name stem, e.g. mippr_white_grid_letter or mippr_white_grid_letter_color. */
  get name() {
    return `mippr_${this.background}_${this.paper}${this.colorPatches ? "_color" : ""}`;
  }

  equals(other) {
    return other instanceof Layout && Object.keys(DEFAULTS).every((k) =>
      Array.isArray(this[k]) ? this[k].every((v, i) => v === other[k][i]) : this[k] === other[k]);
  }
}

/** The Layout whose corner markers these IDs belong to (default box and line sizes). */
export function layoutFromMarkerIds(ids) {
  const wanted = new Set(Array.from(ids, Number));
  for (const colorPatches of [false, true]) {
    for (const background of BACKGROUNDS) {
      for (const paper of Object.keys(PAPERS)) {
        const lay = new Layout({ background, paper, colorPatches });
        if (lay.markerIds().some((i) => wanted.has(i))) return lay;
      }
    }
  }
  throw new Error(
    "No MIPPR sheet markers found in the photo. Photos must be taken on one of the printed " +
      "MIPPR backgrounds (white grid, black grid or checkerboard), with all four corner markers in view."
  );
}

// ── Finding the sheet in a photo ───────────────────────────────────────────

/** Python's round() to an integer: half to even. */
function roundHalfEven(x) {
  const r = Math.round(x);
  return r - x === 0.5 && r % 2 ? r - 1 : r;
}

export function toGray(cv, img) {
  if (img.channels() === 1) return img.clone();
  const gray = new cv.Mat();
  cv.cvtColor(img, gray, img.channels() === 4 ? cv.COLOR_RGBA2GRAY : cv.COLOR_BGR2GRAY);
  return gray;
}

/** A 3-channel BGR copy, as the Python reference expects (4 channels are taken as RGBA). Caller deletes it. */
export function toBgr(cv, img) {
  const n = img.channels();
  if (n === 3) return img.clone();
  const out = new cv.Mat();
  cv.cvtColor(img, out, n === 4 ? cv.COLOR_RGBA2BGR : cv.COLOR_GRAY2BGR);
  return out;
}

/**
 * ArUco 4x4_50 markers -> {id: 4 corners [x, y] in photo px}.
 * A 4-channel image is taken as RGBA (canvas ImageData via cv.matFromImageData), 3 channels as BGR like Python.
 */
export function detectMarkers(cv, img) {
  const gray = toGray(cv, img);
  const dict = cv.getPredefinedDictionary(cv[ARUCO_DICT]);
  const params = new cv.aruco_DetectorParameters();
  const refine = new cv.aruco_RefineParameters(10, 3, true);
  const det = new cv.aruco_ArucoDetector(dict, params, refine);
  const corners = new cv.MatVector();
  const ids = new cv.Mat();
  const rejected = new cv.MatVector();
  try {
    det.detectMarkers(gray, corners, ids, rejected);
    const out = {};
    const idList = ids.data32S; // N x 1 in OpenCV 4.x, 1 x N in 5.x
    for (let k = 0; k < idList.length; k++) {
      const c = corners.get(k);
      const p = c.data32F;
      out[idList[k]] = [[p[0], p[1]], [p[2], p[3]], [p[4], p[5]], [p[6], p[7]]];
      c.delete();
    }
    return out;
  } finally {
    [gray, dict, params, refine, det, corners, ids, rejected].forEach((m) => m.delete());
  }
}

/**
 * Locate a printed MIPPR sheet: layout, px per mm, the photo -> sheet homography from the corner markers,
 * and the grid crossings in photo px (`crossings[row][col] = [x, y]`), refined onto the printed lines.
 * Mirrors find_sheet in sheet.py. Throws an Error with a readable reason.
 */
export function findSheet(cv, img, { pxPerMm = null, layout = null } = {}) {
  let found = detectMarkers(cv, img);
  layout ??= layoutFromMarkerIds(Object.keys(found));
  const expected = layout.markerCornersMm();
  found = Object.fromEntries(Object.entries(found).filter(([k]) => k in expected));
  const keys = Object.keys(found).map(Number).sort((a, b) => a - b);
  if (keys.length < 2) {
    throw new Error(`Found ${keys.length} of the 4 corner markers; at least 2 are needed. ` +
      "Is the whole sheet in the photo?");
  }
  if (pxPerMm == null) {
    // Keep about the photo's own resolution.
    const sides = Object.values(found).map((c) => Math.hypot(c[1][0] - c[0][0], c[1][1] - c[0][1]));
    pxPerMm = pyRound(sides.reduce((a, b) => a + b, 0) / sides.length / layout.markerMm, 1);
  }
  const src = keys.flatMap((k) => found[k].flat());
  const dst = keys.flatMap((k) => expected[k].flat().map((v) => v * pxPerMm));
  const srcMat = cv.matFromArray(src.length / 2, 1, cv.CV_64FC2, src);
  const dstMat = cv.matFromArray(dst.length / 2, 1, cv.CV_64FC2, dst);
  const H = cv.findHomography(srcMat, dstMat);
  const homography = Array.from(H.data64F);
  [srcMat, dstMat, H].forEach((m) => m.delete());
  if (homography.length !== 9) throw new Error("Could not fit the sheet's perspective from the markers.");
  const crossings = refineCrossings(cv, img, layout, homography, pxPerMm);
  return { layout, pxPerMm, homography, crossings, markers: found, markersFound: keys.length };
}

/** Sheet size in px at the sheet's px per mm. */
export function sheetSizePx(sheet) {
  return sheet.layout.sizeMm.map((v) => pyRound(v * sheet.pxPerMm));
}

/** The whole sheet flattened with the marker homography (for margins: patches, scale line). Caller deletes it. */
export function rectifySheet(cv, sheet, img, interpolation = cv.INTER_LINEAR) {
  const [w, h] = sheetSizePx(sheet);
  const H = cv.matFromArray(3, 3, cv.CV_64F, sheet.homography);
  const out = new cv.Mat();
  cv.warpPerspective(img, out, H, new cv.Size(w, h), interpolation, cv.BORDER_REPLICATE, new cv.Scalar());
  H.delete();
  return out;
}

/** Grid size in px at the sheet's px per mm. */
export function gridSizePx(sheet) {
  return sheet.layout.gridSizeMm.map((v) => pyRound(v * sheet.pxPerMm));
}

export function boxPx(sheet) {
  return sheet.layout.boxMm * sheet.pxPerMm;
}

const gridMaps = new WeakMap();

/** remap() maps from the grid crossings: each box warped bilinearly from its four corners. */
function gridMapsOf(sheet) {
  if (gridMaps.has(sheet)) return gridMaps.get(sheet);
  const g = sheet.crossings;
  const [w, h] = gridSizePx(sheet);
  const b = boxPx(sheet);
  const { rows, cols } = sheet.layout;
  const mapX = new Float32Array(w * h);
  const mapY = new Float32Array(w * h);
  const i0 = new Int32Array(w), fu = new Float64Array(w);
  for (let x = 0; x < w; x++) {
    const u = (x + 0.5) / b;
    i0[x] = Math.min(Math.max(Math.floor(u), 0), cols - 1);
    fu[x] = u - i0[x];
  }
  for (let y = 0; y < h; y++) {
    const v = (y + 0.5) / b;
    const j = Math.min(Math.max(Math.floor(v), 0), rows - 1);
    const fv = v - j;
    for (let x = 0; x < w; x++) {
      const i = i0[x], f = fu[x];
      for (let k = 0; k < 2; k++) {
        const top = g[j][i][k] * (1 - f) + g[j][i + 1][k] * f;
        const bot = g[j + 1][i][k] * (1 - f) + g[j + 1][i + 1][k] * f;
        (k ? mapY : mapX)[y * w + x] = top * (1 - fv) + bot * fv - 0.5;
      }
    }
  }
  const maps = { w, h, mapX, mapY };
  gridMaps.set(sheet, maps);
  return maps;
}

/** The grid area only, flattened box by box from the refined crossings: origin at the grid's top-left. Caller deletes it. */
export function rectifyGrid(cv, sheet, img, interpolation = cv.INTER_LINEAR) {
  const { w, h, mapX, mapY } = gridMapsOf(sheet);
  const mx = new cv.Mat(h, w, cv.CV_32FC1);
  const my = new cv.Mat(h, w, cv.CV_32FC1);
  mx.data32F.set(mapX);
  my.data32F.set(mapY);
  const out = new cv.Mat();
  cv.remap(img, out, mx, my, interpolation, cv.BORDER_REPLICATE, new cv.Scalar());
  mx.delete();
  my.delete();
  return out;
}

// ── Grid-crossing refinement (_refine_crossings in sheet.py) ───────────────

function applyH(H, x, y) {
  const z = H[6] * x + H[7] * y + H[8];
  return [(H[0] * x + H[1] * y + H[2]) / z, (H[3] * x + H[4] * y + H[5]) / z];
}

function invert3(m) {
  const [a, b, c, d, e, f, g, h, i] = m;
  const A = e * i - f * h, B = -(d * i - f * g), C = d * h - e * g;
  const det = a * A + b * B + c * C;
  return [A, -(b * i - c * h), b * f - c * e, B, a * i - c * g, -(a * f - c * d), C, -(a * h - b * g), a * e - b * d]
    .map((v) => v / det);
}

function median(values) {
  const a = Float64Array.from(values).sort();
  const n = a.length;
  return n % 2 ? a[(n - 1) / 2] : (a[n / 2 - 1] + a[n / 2]) / 2;
}

/**
 * Grid crossings in photo px, moved onto the printed lines (or checkerboard corners).
 * Pass 1 searches just under half a box wide, a smooth surface is fitted to what it finds,
 * and passes 2 and 3 search ever more narrowly around that prediction.
 */
export function refineCrossings(cv, img, layout, H, ppm) {
  const gray = toGray(cv, img);
  const [w, h] = layout.sizeMm.map((v) => pyRound(v * ppm));
  const canvas = warpPerspectiveLinear(cv, gray, H, w, h);
  gray.delete();
  const { rows, cols } = layout;
  const b = layout.boxMm * ppm;
  const [gx, gy] = layout.gridOriginMm.map((v) => v * ppm);
  const n = (rows + 1) * (cols + 1);
  const ideal = new Float64Array(2 * n);
  for (let r = 0; r <= rows; r++) {
    for (let c = 0; c <= cols; c++) {
      ideal[2 * (r * (cols + 1) + c)] = gx + c * b;
      ideal[2 * (r * (cols + 1) + c) + 1] = gy + r * b;
    }
  }
  let guess = new Float64Array(2 * n);
  let shift, ok;
  try {
    for (const frac of [0.42, 0.25, 0.12]) {
      ({ shift, ok } = searchCrossings(cv, canvas, layout, ideal, guess, Math.trunc(Math.max(4, frac * b)), ppm));
      guess = smoothFit(ideal, shift, ok);
    }
  } finally {
    canvas.delete();
  }
  // Keep measured crossings that agree with the smooth surface; use the surface elsewhere.
  const tol = Math.max(2.0, 0.03 * b);
  const Hinv = invert3(H);
  const out = [];
  for (let r = 0; r <= rows; r++) {
    const row = [];
    for (let c = 0; c <= cols; c++) {
      const k = r * (cols + 1) + c;
      const good = ok[k] && Math.hypot(shift[2 * k] - guess[2 * k], shift[2 * k + 1] - guess[2 * k + 1]) < tol;
      const s = good ? shift : guess;
      row.push(applyH(Hinv, ideal[2 * k] + s[2 * k], ideal[2 * k + 1] + s[2 * k + 1]));
    }
    out.push(row);
  }
  return out;
}

/** Find each crossing within `half` px of ideal + guess on the sheet canvas. Returns {shift from ideal, ok}. */
function searchCrossings(cv, canvas, layout, ideal, guess, half, ppm) {
  const { rows, cols, background } = layout;
  const shift = Float64Array.from(guess);
  const ok = new Uint8Array(ideal.length / 2);
  const W = canvas.cols, Hh = canvas.rows;
  if (background === "checkerboard") {
    const idx = [];
    const start = [];
    for (let r = 1; r < rows; r++) {
      for (let c = 1; c < cols; c++) {
        const k = r * (cols + 1) + c;
        idx.push(k);
        start.push([Math.fround(ideal[2 * k] + guess[2 * k]), Math.fround(ideal[2 * k + 1] + guess[2 * k + 1])]);
      }
    }
    const refined = cornerSubPix(cv, canvas, start, [half, half], [-1, -1], { maxCount: 60, epsilon: 0.01 });
    idx.forEach((k, i) => {
      const dx = Math.fround(refined[i][0] - start[i][0]);
      const dy = Math.fround(refined[i][1] - start[i][1]);
      if (Math.hypot(dx, dy) < half) {
        shift[2 * k] += dx;
        shift[2 * k + 1] += dy;
        ok[k] = 1;
      }
    });
    return { shift, ok };
  }
  const data = canvas.data;
  const invert = background === "white_grid";
  const lw = Math.max(1.0, layout.lineMm * ppm);
  const size = 2 * half + 1;
  const keep = Array.from({ length: size }, (_, i) => Math.abs(i - half) > 2 * lw + 2);
  // On the black grid the outer border is a white line on white paper, so it can't be seen.
  const innerOnly = background === "black_grid";
  const px = new Float64Array(size), py = new Float64Array(size);
  for (let r = 0; r <= rows; r++) {
    for (let c = 0; c <= cols; c++) {
      if (innerOnly && (r === 0 || r === rows || c === 0 || c === cols)) continue;
      const k = r * (cols + 1) + c;
      const x0 = ideal[2 * k] + guess[2 * k], y0 = ideal[2 * k + 1] + guess[2 * k + 1];
      const xi = roundHalfEven(x0), yi = roundHalfEven(y0);
      if (xi - half < 0 || yi - half < 0 || xi + half + 1 > W || yi + half + 1 > Hh) continue;
      px.fill(0);
      py.fill(0);
      for (let i = 0; i < size; i++) {
        const row = (yi - half + i) * W + xi - half;
        for (let j = 0; j < size; j++) {
          const v = invert ? 255 - data[row + j] : data[row + j];
          if (keep[i]) px[j] += v;
          if (keep[j]) py[i] += v;
        }
      }
      // The band of the crossing line, flat along the other axis, is left out of each profile.
      const dx = peak(px, half), dy = peak(py, half);
      if (dx !== null && dy !== null) {
        shift[2 * k] = guess[2 * k] + dx + (xi - x0);
        shift[2 * k + 1] = guess[2 * k + 1] + dy + (yi - y0);
        ok[k] = 1;
      }
    }
  }
  return { shift, ok };
}

/** Sub-pixel offset of the profile's peak from the window centre, or null if there is no clear line. */
function peak(profile, half) {
  const med = median(profile);
  const p = Array.from(profile, (v) => v - med);
  let k = 0;
  for (let i = 1; i < p.length; i++) if (p[i] > p[k]) k = i;
  if (p[k] <= 0 || p[k] < 4 * (median(p.map(Math.abs)) + 1e-6)) return null;
  let sw = 0, swi = 0;
  for (let i = Math.max(0, k - 3); i < Math.min(p.length, k + 4); i++) {
    const wt = Math.max(p[i], 0);
    sw += wt;
    swi += i * wt;
  }
  return swi / sw - half;
}

/** Least-squares cubic surface through the found shifts, with one round of outlier removal. */
function smoothFit(ideal, shift, ok, degree = 3) {
  const n = ok.length;
  if (ok.reduce((a, v) => a + v, 0) < 10) return new Float64Array(2 * n);
  let sx = -Infinity, sy = -Infinity;
  for (let k = 0; k < n; k++) {
    sx = Math.max(sx, ideal[2 * k]);
    sy = Math.max(sy, ideal[2 * k + 1]);
  }
  const terms = [];
  for (let i = 0; i <= degree; i++) for (let j = 0; j <= degree - i; j++) terms.push([i, j]);
  const A = [];
  for (let k = 0; k < n; k++) {
    const x = (ideal[2 * k] / sx) * 2 - 1, y = (ideal[2 * k + 1] / sy) * 2 - 1;
    A.push(terms.map(([i, j]) => x ** i * y ** j));
  }
  let mask = Uint8Array.from(ok);
  let fit;
  for (let round = 0; round < 2; round++) {
    const coef = leastSquares(A, shift, mask);
    fit = new Float64Array(2 * n);
    const err = new Float64Array(n);
    for (let k = 0; k < n; k++) {
      for (let t = 0; t < terms.length; t++) {
        fit[2 * k] += A[k][t] * coef[t][0];
        fit[2 * k + 1] += A[k][t] * coef[t][1];
      }
      err[k] = Math.hypot(fit[2 * k] - shift[2 * k], fit[2 * k + 1] - shift[2 * k + 1]);
    }
    const limit = Math.max(2.0, 3 * median(err.filter((_, k) => ok[k])));
    mask = Uint8Array.from(ok, (v, k) => v && err[k] < limit);
  }
  return fit;
}

/** Least squares A[mask] coef = shift[mask] for the x and y columns (normal equations, partial pivoting). */
function leastSquares(A, shift, mask) {
  const m = A[0].length;
  const M = Array.from({ length: m }, () => new Float64Array(m + 2));
  A.forEach((a, k) => {
    if (!mask[k]) return;
    for (let i = 0; i < m; i++) {
      for (let j = 0; j < m; j++) M[i][j] += a[i] * a[j];
      M[i][m] += a[i] * shift[2 * k];
      M[i][m + 1] += a[i] * shift[2 * k + 1];
    }
  });
  for (let col = 0; col < m; col++) {
    let p = col;
    for (let r = col + 1; r < m; r++) if (Math.abs(M[r][col]) > Math.abs(M[p][col])) p = r;
    [M[col], M[p]] = [M[p], M[col]];
    for (let r = 0; r < m; r++) {
      if (r === col) continue;
      const f = M[r][col] / M[col][col];
      for (let j = col; j < m + 2; j++) M[r][j] -= f * M[col][j];
    }
  }
  return M.map((row, i) => [row[m] / row[i], row[m + 1] / row[i]]);
}

// ── White balance (white_balance in calibration.py) ────────────────────────

/** {patch name: [B, G, R] channel values} of the printed patches (white, grey and any coloured ones), from the marker homography. */
export function patchPixels(cv, sheet, img, inset = 2.0) {
  const bgr = toBgr(cv, img);
  const canvas = rectifySheet(cv, sheet, bgr);
  bgr.delete();
  const ppm = sheet.pxPerMm;
  const out = {};
  for (const [name, [x, y, w, h]] of Object.entries({ ...sheet.layout.patchesMm(), ...sheet.layout.colorPatchesMm() })) {
    const y0 = Math.trunc((y + inset) * ppm), y1 = Math.trunc((y + h - inset) * ppm);
    const x0 = Math.trunc((x + inset) * ppm), x1 = Math.trunc((x + w - inset) * ppm);
    const n = Math.max(0, y1 - y0) * Math.max(0, x1 - x0);
    const ch = [new Uint8Array(n), new Uint8Array(n), new Uint8Array(n)];
    const data = canvas.data;
    let i = 0;
    for (let yy = y0; yy < y1; yy++) {
      for (let xx = x0; xx < x1; xx++, i++) {
        const o = 3 * (yy * canvas.cols + xx);
        ch[0][i] = data[o];
        ch[1][i] = data[o + 1];
        ch[2][i] = data[o + 2];
      }
    }
    out[name] = ch;
  }
  canvas.delete();
  return out;
}

/**
 * Per-channel gains (B, G, R) that make the printed white patch neutral, and a report of how neutral
 * the grey patch came out (the same keys as Python, for run.json).
 */
export function whiteBalance(cv, sheet, img) {
  const px = patchPixels(cv, sheet, img);
  const mean = (a) => a.reduce((s, v) => s + v, 0) / a.length;
  const white = px.white.map(mean);
  const gains = white.map((v) => 240.0 / Math.max(v, 1.0));
  const grey = px.grey.map((a, i) => mean(a) * gains[i]);
  const r = (a, d) => a.map((v) => pyRound(v, d));
  const report = {
    white_patch_bgr: r(white, 1),
    gains_bgr: r(gains, 3),
    grey_patch_after_bgr: r(grey, 1),
    grey_spread_after: Math.max(...grey) - Math.min(...grey),
  };
  // Coloured patches: their colour after white balance, to compare photos of one printout (no result uses them).
  const colors = Object.keys(sheet.layout.colorPatchesMm());
  if (colors.length) {
    report.color_patches_after_bgr = Object.fromEntries(colors.map((k) =>
      [k, r(px[k].map((a, i) => Math.min(255, Math.max(0, mean(a) * gains[i]))), 1)]));
  }
  return { gains, report };
}

