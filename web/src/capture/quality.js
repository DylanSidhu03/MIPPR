// Part 1: browser port of the photo quality check in pipeline/mippr/capture/calibration.py
// (measure_quality, check_quality, QualityLimits, Problem). Same codes, messages and limits;
// the metric keys are Python's, as they go into run.json. Parity is checked by web/tests/quality.test.mjs.
// OpenCV.js is passed in as `cv`; a 3-channel photo is BGR, 4 channels RGBA (as in sheet.js).
import { boxPx, detectMarkers, layoutFromMarkerIds, patchPixels, pyRound, toBgr } from "./sheet.js";

/** Thresholds of `checkQuality`, chosen on degraded synthetic photos (see pipeline/mippr/capture/README.md). */
export const QUALITY_LIMITS = Object.freeze({
  minPxPerMm: 10.0, // a 0.5 mm particle spans >= 5 px (about 20 px of area)
  maxEdgeMm: 0.3, // edges spread over more than this (about Gaussian sigma 0.12 mm) ...
  sharpEdgePx: 4.0, // ... and over more than this many px (a pixel-sharp edge measures 2-3 px)
  maxEdgePx: 6.0, // the limit when the scale is unknown (no markers): 0.30 mm at 20 px per mm
  minWhite: 110.0, // the white patch (or the photo's brightest 1%) at least this grey level
  maxClipped: 0.1, // share of the box interiors (whole photo without a sheet) at 250 or more
  glareMm2: 0.5, // a colourless blob inside a box, brighter than paper (1.2 x white patch), this large
  minLightRatio: 0.6, // darkest / brightest white box (5th / 95th percentile)
  maxGreySpread: 15.0, // grey patch channel spread after white balance (grey levels)
});

/** One reason a photo can't give good results: a stable `code` and a plain `message`. */
export class Problem {
  constructor(code, message, value = null, limit = null) {
    Object.assign(this, { code, message, value, limit });
    Object.freeze(this);
  }

  asDict() {
    return { code: this.code, message: this.message, value: this.value, limit: this.limit };
  }
}

export const CORNERS = Object.freeze(["top left", "top right", "bottom right", "bottom left"]); // Layout.markerIds() order

// ── numpy helpers ──────────────────────────────────────────────────────────

function roundHalfEven(x) {
  const r = Math.round(x);
  return r - x === 0.5 && r % 2 ? r - 1 : r;
}

/** np.percentile (linear) of numbers. */
function percentile(values, q) {
  const a = Float64Array.from(values).sort();
  const pos = ((a.length - 1) * q) / 100;
  const lo = Math.floor(pos);
  const hi = Math.min(lo + 1, a.length - 1);
  return a[lo] + (a[hi] - a[lo]) * (pos - lo);
}

function median(values) {
  return percentile(values, 50);
}

function mean(values) {
  let s = 0;
  for (const v of values) s += v;
  return s / values.length;
}

function matOf(cv, type, rows, cols, data) {
  const m = new cv.Mat(rows, cols, type);
  m.data.set(data);
  return m;
}

function morph(cv, op, src, size) {
  const [kw, kh] = size;
  const k = cv.Mat.ones(kh, kw, cv.CV_8U);
  const out = new cv.Mat();
  cv[op](src, out, k, new cv.Point(-1, -1), 1, cv.BORDER_CONSTANT, cv.morphologyDefaultBorderValue());
  k.delete();
  return out;
}

function fillPolys(cv, mask, polys) {
  const vec = new cv.MatVector();
  for (const p of polys) {
    const m = cv.matFromArray(p.length, 1, cv.CV_32SC2, p.flatMap(([x, y]) => [roundHalfEven(x), roundHalfEven(y)]));
    vec.push_back(m);
    m.delete();
  }
  cv.fillPoly(mask, vec, new cv.Scalar(1));
  vec.delete();
}

// ── Metrics ────────────────────────────────────────────────────────────────

/**
 * How many px the image's strong edges are spread over, [across x, across y] (NaN: fewer than 50 edges).
 * For each strong edge, its local contrast (max - min within `window`) divided by its steepest gradient;
 * the 25th percentile over the edges. `mask` (Uint8Array, optional) limits where edges are taken.
 */
export function edgeWidthPx(cv, gray, mask = null, window = 21) {
  const g = new cv.Mat();
  gray.convertTo(g, cv.CV_32F);
  const dil = morph(cv, "dilate", g, [window, window]);
  const ero = morph(cv, "erode", g, [window, window]);
  const n = gray.rows * gray.cols;
  const contrast = new Float32Array(n);
  const [dd, ed] = [dil.data32F, ero.data32F];
  for (let i = 0; i < n; i++) contrast[i] = dd[i] - ed[i];
  [dil, ero].forEach((m) => m.delete());
  const sobel = (dx, dy) => {
    const s = new cv.Mat();
    cv.Sobel(g, s, cv.CV_32F, dx, dy, 3, 1, 0, cv.BORDER_DEFAULT);
    const a = new Float32Array(n);
    const sd = s.data32F;
    for (let i = 0; i < n; i++) a[i] = Math.abs(sd[i]) / 8;
    s.delete();
    return a;
  };
  const gx = sobel(1, 0), gy = sobel(0, 1);
  g.delete();
  const out = [];
  for (const [grad, other, size] of [[gx, gy, [3, 1]], [gy, gx, [1, 3]]]) {
    const gm = matOf(cv, cv.CV_32F, gray.rows, gray.cols, new Uint8Array(grad.buffer));
    const top = morph(cv, "dilate", gm, size);
    const w = [];
    const lim = window + 1;
    const td = top.data32F;
    for (let i = 0; i < n; i++) {
      const gr = grad[i], c = contrast[i];
      if (gr >= td[i] && c >= 40 && gr > other[i] && gr >= Math.fround(c / lim) && (!mask || mask[i])) {
        w.push(Math.fround(c / gr));
      }
    }
    [gm, top].forEach((m) => m.delete());
    out.push(w.length >= 50 ? percentile(w, 25) : NaN);
  }
  return out;
}

/** The grid area in photo px (from the refined crossings), shrunk by a third of a box. */
function gridMask(cv, sheet, rows, cols) {
  const c = sheet.crossings;
  const R = c.length - 1, C = c[0].length - 1;
  const ring = [...c[0]];
  for (let r = 1; r <= R; r++) ring.push(c[r][C]);
  for (let k = C - 1; k >= 0; k--) ring.push(c[R][k]);
  for (let r = R - 1; r > 0; r--) ring.push(c[r][0]);
  const mask = cv.Mat.zeros(rows, cols, cv.CV_8U);
  fillPolys(cv, mask, [ring]);
  const k = Math.max(3, Math.trunc(boxPx(sheet) / 3));
  const out = morph(cv, "erode", mask, [k, k]);
  const data = Uint8Array.from(out.data);
  [mask, out].forEach((m) => m.delete());
  return data;
}

/** The middle `keep` of every box in photo px: paper or particle, no printed lines. */
function boxMask(cv, sheet, rows, cols, keep = 0.7) {
  const c = sheet.crossings;
  const mask = cv.Mat.zeros(rows, cols, cv.CV_8U);
  for (let r = 0; r < sheet.layout.rows; r++) {
    for (let col = 0; col < sheet.layout.cols; col++) {
      const quad = [c[r][col], c[r][col + 1], c[r + 1][col + 1], c[r + 1][col]];
      const mid = [0, 1].map((k) => (quad[0][k] + quad[1][k] + quad[2][k] + quad[3][k]) / 4);
      fillPolys(cv, mask, [quad.map((p) => p.map((v, k) => mid[k] + (v - mid[k]) * keep))]);
    }
  }
  const data = Uint8Array.from(mask.data);
  mask.delete();
  return data;
}

/** 90th-percentile grey level near the centre of every white box (paper level, not the particle). */
function whiteBoxes(sheet, gray) {
  const lay = sheet.layout;
  if (lay.background === "black_grid") return [];
  const c = sheet.crossings;
  const half = Math.max(2, Math.trunc(boxPx(sheet) * 0.3));
  const W = gray.cols, H = gray.rows, data = gray.data;
  const levels = [];
  for (let r = 0; r < lay.rows; r++) {
    for (let col = 0; col < lay.cols; col++) {
      if (lay.background === "checkerboard" && (r + col) % 2) continue;
      const pts = [c[r][col], c[r][col + 1], c[r + 1][col], c[r + 1][col + 1]];
      const x = roundHalfEven((pts[0][0] + pts[1][0] + pts[2][0] + pts[3][0]) / 4);
      const y = roundHalfEven((pts[0][1] + pts[1][1] + pts[2][1] + pts[3][1]) / 4);
      const win = [];
      for (let yy = Math.max(0, y - half); yy < Math.min(H, y + half); yy++) {
        for (let xx = Math.max(0, x - half); xx < Math.min(W, x + half); xx++) win.push(data[yy * W + xx]);
      }
      if (win.length) levels.push(percentile(win, 90));
    }
  }
  return levels;
}

/**
 * The numbers `checkQuality` judges (also worth keeping in run.json), with Python's keys:
 * markers_found (of 4; null if no sheet's markers at all), missing_corners, px_per_mm, edge_width_px [x, y],
 * edge_width_mm, white_level, clipped_share, and with a sheet: white_clipped, glare_mm2, light_ratio, grey_spread.
 */
export function measureQuality(cv, photo, sheet = null) {
  const bgr = toBgr(cv, photo);
  const gray = new cv.Mat();
  cv.cvtColor(bgr, gray, cv.COLOR_BGR2GRAY);
  try {
    return measure(cv, bgr, gray, sheet);
  } finally {
    [bgr, gray].forEach((m) => m.delete());
  }
}

function measure(cv, bgr, gray, sheet) {
  const m = {};
  const rows = gray.rows, cols = gray.cols, n = rows * cols;
  const px3 = bgr.data;

  // Markers: which of the four corners were found.
  const found = detectMarkers(cv, bgr);
  let layout = sheet ? sheet.layout : null;
  if (!layout) {
    try {
      layout = layoutFromMarkerIds(Object.keys(found));
    } catch {
      layout = null;
    }
  }
  let ppm = null;
  if (!layout) {
    m.markers_found = null;
    m.missing_corners = [...CORNERS];
  } else {
    const ids = layout.markerIds();
    m.missing_corners = CORNERS.filter((_, i) => !(ids[i] in found));
    m.markers_found = 4 - m.missing_corners.length;
    if (sheet) ppm = sheet.pxPerMm;
    else {
      // The markers alone still give the scale.
      const sides = ids.filter((i) => i in found).map((i) => {
        const c = found[i];
        return mean(c.map((p, k) => Math.hypot(c[(k + 1) % 4][0] - p[0], c[(k + 1) % 4][1] - p[1])));
      });
      ppm = sides.length ? mean(sides) / layout.markerMm : null;
    }
  }
  m.px_per_mm = ppm == null ? null : pyRound(ppm, 2);

  // Blur: how wide the printed edges (or, without a sheet, any strong edges) are.
  const grid = sheet ? gridMask(cv, sheet, rows, cols) : null;
  const window = ppm ? Math.trunc(Math.max(7, roundHalfEven(1.5 * ppm)) / 2) * 2 + 1 : 21;
  const [wx, wy] = edgeWidthPx(cv, gray, grid, window);
  m.edge_width_px = [wx, wy].map((v) => (Number.isNaN(v) ? null : pyRound(v, 2)));
  const width = !Number.isNaN(wx) && !Number.isNaN(wy) ? Math.max(wx, wy) : Number.isNaN(wx) ? wy : wx;
  m.edge_width_mm = ppm == null || Number.isNaN(width) ? null : pyRound(width / ppm, 3);

  // Exposure: the printed white patch with a sheet, else the photo's brightest 1%.
  const boxes = sheet ? boxMask(cv, sheet, rows, cols) : null;
  let clipped = 0, inBoxes = 0;
  for (let i = 0; i < n; i++) {
    if (boxes && !boxes[i]) continue;
    inBoxes++;
    if (Math.max(px3[3 * i], px3[3 * i + 1], px3[3 * i + 2]) >= 250) clipped++;
  }
  m.clipped_share = pyRound(clipped / inBoxes, 4);
  let patches;
  if (sheet) {
    // Medians, because under lens distortion the patch's printed frame can creep into the crop.
    const px = patchPixels(cv, sheet, bgr);
    patches = Object.fromEntries(Object.entries(px).map(([k, ch]) => [k, ch.map(median)]));
    m.white_level = pyRound(mean(patches.white), 1);
    const [b, g, r] = px.white;
    let whiteClipped = 0;
    for (let i = 0; i < b.length; i++) if (Math.max(b[i], g[i], r[i]) >= 250) whiteClipped++;
    m.white_clipped = pyRound(whiteClipped / b.length, 3);
  } else {
    m.white_level = pyRound(percentile(gray.data, 99), 1);
  }

  if (sheet) {
    // Glare: the largest colourless blob inside any box that is brighter than paper can be.
    const level = Math.min(250.0, 1.2 * m.white_level);
    const shiny = new Uint8Array(n);
    for (let i = 0; i < n; i++) {
      shiny[i] = boxes[i] && Math.min(px3[3 * i], px3[3 * i + 1], px3[3 * i + 2]) >= level ? 1 : 0;
    }
    const src = matOf(cv, cv.CV_8U, rows, cols, shiny);
    const labels = new cv.Mat(), stats = new cv.Mat(), centroids = new cv.Mat();
    const count = cv.connectedComponentsWithStats(src, labels, stats, centroids, 8, cv.CV_32S);
    let largest = 0;
    for (let k = 1; k < count; k++) largest = Math.max(largest, stats.intAt(k, cv.CC_STAT_AREA));
    [src, labels, stats, centroids].forEach((mm) => mm.delete());
    m.glare_mm2 = pyRound(count > 1 ? largest / ppm ** 2 : 0.0, 2);
    // Uneven light (e.g. the phone's shadow): darkest against brightest white boxes.
    const levels = whiteBoxes(sheet, gray);
    m.light_ratio = levels.length >= 10
      ? pyRound(percentile(levels, 5) / Math.max(percentile(levels, 95), 1.0), 3) : null;
    // Colour cast left after white balance: the grey patch should come out grey.
    const greyAfter = patches.grey.map((v, k) => v * (240.0 / Math.max(patches.white[k], 1.0)));
    m.grey_spread = pyRound(Math.max(...greyAfter) - Math.min(...greyAfter), 1);
  }
  return m;
}

/** Python's f"{x:.1f}" (round half to even on exact ties). */
function fixed1(x) {
  return pyRound(x, 1).toFixed(1);
}

/**
 * Reasons a photo can't give good results, before anything else runs: a list of Problems, empty = fine.
 * With `sheet` (from findSheet) the checks look inside the grid and use the printed patches; without it
 * the checks that don't need it run on the whole photo. Pass `metrics` from measureQuality to avoid
 * measuring twice, and `limits` to override any of QUALITY_LIMITS.
 */
export function checkQuality(cv, photo, sheet = null, { limits = {}, metrics = null } = {}) {
  const L = { ...QUALITY_LIMITS, ...limits };
  const m = metrics ?? measureQuality(cv, photo, sheet);
  const probs = [];
  if (m.markers_found == null) {
    probs.push(new Problem("no_markers", "No MIPPR sheet found. Photos must be taken on one of the printed " +
      "MIPPR backgrounds (white grid, black grid or checkerboard), with the whole " +
      "sheet and all four black corner squares in view.", 0, 4));
  } else if (m.missing_corners.length) {
    probs.push(new Problem("marker_missing", `Corner marker missing (${m.missing_corners.join(", ")}). Keep ` +
      "all four black corner squares in the photo, uncovered and in focus.", m.markers_found, 4));
  }

  const ppm = m.px_per_mm;
  if (ppm != null && ppm < L.minPxPerMm) {
    probs.push(new Problem("low_resolution", `Not enough detail: a 0.5 mm particle would be only ${fixed1(ppm * 0.5)} ` +
      "pixels across. Use the camera's full resolution (no zoom, no reduced size) and fill " +
      "the frame with the sheet.", ppm, L.minPxPerMm));
  }

  const widths = m.edge_width_px.filter((v) => v != null);
  const edgePx = widths.length ? Math.max(...widths) : null;
  let value, limit, blurry;
  if (m.edge_width_mm != null) {
    [value, limit] = [m.edge_width_mm, L.maxEdgeMm];
    blurry = value > limit && edgePx > L.sharpEdgePx;
  } else {
    [value, limit] = [edgePx, L.maxEdgePx];
    blurry = value != null && value > limit;
  }
  if (blurry) {
    probs.push(new Problem("blurry", "The photo is blurry. Hold the phone still, tap the sheet to focus, and " +
      "use more light.", value, limit));
  }

  if (m.white_level < L.minWhite) {
    probs.push(new Problem("too_dark", "The photo is too dark. Add light or move to a brighter place (no flash).",
      m.white_level, L.minWhite));
  }
  const overexposed = m.clipped_share > L.maxClipped || (m.white_clipped ?? 0) > 0.5;
  if (overexposed) {
    probs.push(new Problem("overexposed", "The photo is too bright: parts of it are pure white, so pale " +
      "particles disappear. Use less light or tap the sheet to set the exposure.", m.clipped_share, L.maxClipped));
  }

  if (sheet) {
    if (!overexposed && m.glare_mm2 >= L.glareMm2) {
      probs.push(new Problem("glare", "Glare on the sheet. Move the light to the side or use diffuse light, and " +
        "don't use the flash.", m.glare_mm2, L.glareMm2));
    }
    if (m.light_ratio != null && m.light_ratio < L.minLightRatio) {
      probs.push(new Problem("uneven_light", "The light is uneven (a shadow?). Light the sheet evenly and keep " +
        "your shadow and the phone's off it.", m.light_ratio, L.minLightRatio));
    }
    if (!overexposed && m.grey_spread > L.maxGreySpread) {
      probs.push(new Problem("color_cast", "Colours may be off: the grey patch is still tinted after white " +
        "balance. Use one kind of light (daylight or one lamp), not a mix.", m.grey_spread, L.maxGreySpread));
    }
  }
  return probs;
}
