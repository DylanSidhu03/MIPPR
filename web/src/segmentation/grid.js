// Part 2: browser port of pipeline/mippr/segmentation/grid.py (per-box segmentation on the printed grids).
// Input is the flattened grid (origin at the grid's top-left corner), CV_8UC3 or CV_8UC4 (alpha ignored).
// Functions take the OpenCV.js module as `cv`; returned Mats are the caller's to delete.
// Parity with the Python reference is checked by web/tests/segment.test.mjs.
import { pyRound } from "../capture/sheet.js";
import { fillHoles, hysteresis, refineEdges } from "./edges.js";

export const GRID_SEGMENT_DEFAULTS = Object.freeze({
  blurSigma: 1.0,
  high: 60.0,
  low: 25.0,
  minAreaPx: 9,
  lineMarginMm: 0.25, // added to each side of a printed line (blur, print spread)
  edgeFraction: 0.5,
  insetFrac: 0.15, // box border left out when estimating its background colour
});

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

/** {band, half, outer}: band is a CV_8UC1 0/1 mask, true on the printed lines (or checkerboard edges) plus a margin. */
export function lineBand(cv, layout, pxPerMm, [h, w], marginMm) {
  const b = layout.boxMm * pxPerMm;
  const half = Math.max(1.0, (layout.lineMm / 2 + marginMm) * pxPerMm);
  // The outer border is twice as wide: its crossings can't always be seen, so they can be ~1 px off.
  const outer = half + marginMm * pxPerMm;
  const band = cv.Mat.zeros(h, w, cv.CV_8UC1);
  const m = band.data;
  for (let c = 0; c <= layout.cols; c++) {
    const x = c * b;
    const hw = c === 0 || c === layout.cols ? outer : half;
    const x0 = Math.max(0, Math.floor(x - hw));
    const x1 = Math.min(w, Math.ceil(x + hw) + 1);
    for (let y = 0; y < h; y++) if (x1 > x0) m.fill(1, y * w + x0, y * w + x1);
  }
  for (let r = 0; r <= layout.rows; r++) {
    const y = r * b;
    const hw = r === 0 || r === layout.rows ? outer : half;
    const y0 = Math.max(0, Math.floor(y - hw));
    const y1 = Math.min(h, Math.ceil(y + hw) + 1);
    if (y1 > y0) m.fill(1, y0 * w, y1 * w);
  }
  return { band, half, outer };
}

/** True (1) in each box's top-left label corner; null when the sheet has no box labels. */
function labelZones(layout, pxPerMm, h, w) {
  if (!layout.boxLabels) return null;
  const b = layout.boxMm * pxPerMm;
  const [zw, zh] = layout.labelZoneMm.map((v) => v * pxPerMm);
  const zones = new Uint8Array(h * w);
  let any = false;
  for (let r = 0; r < layout.rows; r++) {
    for (let c = 0; c < layout.cols; c++) {
      const x0 = Math.trunc(c * b);
      const y0 = Math.trunc(r * b);
      const x1 = Math.min(w, Math.trunc(x0 + zw));
      for (let y = y0; y < Math.min(h, Math.trunc(y0 + zh)); y++) {
        if (x1 > x0) {
          zones.fill(1, y * w + x0, y * w + x1);
          any = true;
        }
      }
    }
  }
  return any ? zones : null;
}

/** [row, col] of the box containing point (x, y) of the flattened grid, clipped to the grid. */
export function boxOf(layout, pxPerMm, x, y) {
  const b = layout.boxMm * pxPerMm;
  return [Math.min(layout.rows - 1, Math.max(0, floorDiv(y, b))), Math.min(layout.cols - 1, Math.max(0, floorDiv(x, b)))];
}

/** Float32Array (rows x cols x 3) of each box's median colour, its border left out. */
function backgroundColors(img, layout, pxPerMm, insetFrac) {
  const b = layout.boxMm * pxPerMm;
  const { rows: h, cols: w } = img;
  const ch = img.channels();
  const px = img.data;
  const out = new Float32Array(layout.rows * layout.cols * 3);
  const hist = new Uint32Array(3 * 256);
  for (let r = 0; r < layout.rows; r++) {
    for (let c = 0; c < layout.cols; c++) {
      const y0 = Math.trunc(r * b + insetFrac * b);
      const y1 = Math.min(h, Math.trunc((r + 1) * b - insetFrac * b));
      const x0 = Math.trunc(c * b + insetFrac * b);
      const x1 = Math.min(w, Math.trunc((c + 1) * b - insetFrac * b));
      hist.fill(0);
      for (let y = y0; y < y1; y++) {
        for (let i = (y * w + x0) * ch, end = (y * w + x1) * ch; i < end; i += ch) {
          hist[px[i]]++;
          hist[256 + px[i + 1]]++;
          hist[512 + px[i + 2]]++;
        }
      }
      const n = Math.max(0, y1 - y0) * Math.max(0, x1 - x0);
      for (let k = 0; k < 3; k++) {
        const nth = (j) => {
          let seen = 0;
          for (let v = 0; v < 256; v++) if ((seen += hist[k * 256 + v]) > j) return v;
          return NaN;
        };
        const med = n % 2 ? nth(n >> 1) : (nth(n / 2 - 1) + nth(n / 2)) / 2;
        out[(r * layout.cols + c) * 3 + k] = med;
      }
    }
  }
  return out;
}

function boxIndex(n, b, count) {
  return Int32Array.from({ length: n }, (_, i) => Math.min(floorDiv(i, b), count - 1));
}

/** The background colour expected behind every pixel (CV_32FC3): each box's median colour, filled across the box. */
export function backgroundImage(cv, img, layout, pxPerMm, insetFrac = GRID_SEGMENT_DEFAULTS.insetFrac) {
  const b = layout.boxMm * pxPerMm;
  const { rows: h, cols: w } = img;
  const bg = backgroundColors(img, layout, pxPerMm, insetFrac);
  const rows = boxIndex(h, b, layout.rows);
  const cols = boxIndex(w, b, layout.cols);
  const out = new cv.Mat(h, w, cv.CV_32FC3);
  const o = out.data32F;
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const s = (rows[y] * layout.cols + cols[x]) * 3;
      const i = (y * w + x) * 3;
      o[i] = bg[s];
      o[i + 1] = bg[s + 1];
      o[i + 2] = bg[s + 2];
    }
  }
  return out;
}

/** Inside each line band, use the smaller of the values just outside it on either side. */
function bridge(d, h, w, layout, b, half, outer) {
  for (let c = 0; c <= layout.cols; c++) {
    const k = Math.ceil(c === 0 || c === layout.cols ? outer : half) + 1;
    const x = pyRound(c * b);
    const lo = Math.max(0, x - k + 1);
    const hi = Math.min(w, x + k);
    const xl = Math.max(0, x - k);
    const xr = Math.min(w - 1, x + k);
    for (let y = 0; y < h; y++) {
      const row = y * w;
      const left = c === 0 ? 0 : d[row + xl]; // outside the grid counts as background
      const right = c === layout.cols ? 0 : d[row + xr];
      if (hi > lo) d.fill(Math.min(left, right), row + lo, row + hi);
    }
  }
  for (let r = 0; r <= layout.rows; r++) {
    const k = Math.ceil(r === 0 || r === layout.rows ? outer : half) + 1;
    const y = pyRound(r * b);
    const lo = Math.max(0, y - k + 1);
    const hi = Math.min(h, y + k);
    const top = d.slice(Math.max(0, y - k) * w, Math.max(0, y - k) * w + w);
    const bot = d.slice(Math.min(h - 1, y + k) * w, Math.min(h - 1, y + k) * w + w);
    for (let x = 0; x < w; x++) {
      const v = Math.min(r === 0 ? 0 : top[x], r === layout.rows ? 0 : bot[x]);
      for (let yy = lo; yy < hi; yy++) d[yy * w + x] = v;
    }
  }
}

/** The printed box label in each corner is bridged from just below it and just right of it. */
function bridgeLabels(d, h, w, layout, b, pxPerMm) {
  const [zw, zh] = layout.labelZoneMm.map((v) => Math.ceil(v * pxPerMm));
  for (let r = 0; r < layout.rows; r++) {
    for (let c = 0; c < layout.cols; c++) {
      const x0 = Math.trunc(c * b);
      const y0 = Math.trunc(r * b);
      const x1 = Math.min(w - 1, x0 + zw);
      const y1 = Math.min(h - 1, y0 + zh);
      const below = d.slice(y1 * w + x0, y1 * w + x1);
      for (let y = y0; y < y1; y++) {
        const right = d[y * w + x1];
        for (let x = x0; x < x1; x++) d[y * w + x] = Math.min(below[x - x0], right);
      }
    }
  }
}

function toThreeChannels(cv, img) {
  if (img.channels() === 3) return img.clone();
  if (img.channels() !== 4) throw new Error("segmentGrid needs a colour image (3 or 4 channels)");
  const out = new cv.Mat();
  cv.cvtColor(img, out, cv.COLOR_RGBA2RGB);
  return out;
}

/** {diff, band}: largest colour-channel difference from the pixel's own box background, bridged across lines. */
function difference(cv, img, layout, pxPerMm, params) {
  const b = layout.boxMm * pxPerMm;
  const { rows: h, cols: w } = img;
  const bgImg = backgroundImage(cv, img, layout, pxPerMm, params.insetFrac);
  const f = new cv.Mat();
  img.convertTo(f, cv.CV_32F);
  const p = new cv.Mat();
  cv.GaussianBlur(f, p, new cv.Size(0, 0), params.blurSigma);
  const diff = new cv.Mat(h, w, cv.CV_32FC1);
  const d = diff.data32F;
  const pv = p.data32F;
  const bv = bgImg.data32F;
  for (let i = 0, j = 0; i < d.length; i++, j += 3) {
    d[i] = Math.max(Math.abs(pv[j] - bv[j]), Math.abs(pv[j + 1] - bv[j + 1]), Math.abs(pv[j + 2] - bv[j + 2]));
  }
  [bgImg, f, p].forEach((m) => m.delete());
  const { band, half, outer } = lineBand(cv, layout, pxPerMm, [h, w], params.lineMarginMm);
  bridge(d, h, w, layout, b, half, outer);
  // The printed box label in each corner is masked like the lines: no detection starts there,
  // and a particle reaching into it is bridged from below and the right.
  const zones = labelZones(layout, pxPerMm, h, w);
  if (zones) {
    bridgeLabels(d, h, w, layout, b, pxPerMm);
    const m = band.data;
    for (let i = 0; i < m.length; i++) m[i] |= zones[i];
  }
  return { diff, band };
}

/**
 * {labels, diff, band}: CV_32SC1 labels (0 = background, 1..n), the CV_32FC1 difference map and the
 * CV_8UC1 0/1 line band. Box-by-box difference, bridging across lines and label corners, hysteresis,
 * half-maximum edges, hole filling and the minimum area.
 */
export function segmentGrid(cv, rectified, layout, pxPerMm, params = {}) {
  const p = { ...GRID_SEGMENT_DEFAULTS, ...params };
  const img = toThreeChannels(cv, rectified);
  const { diff, band } = difference(cv, img, layout, pxPerMm, p);
  img.delete();
  const strong = hysteresis(cv, diff, p.low, p.high, band);
  let mask = fillHoles(cv, strong);
  strong.delete();
  if (p.edgeFraction) {
    const refined = refineEdges(cv, mask, diff, p.edgeFraction);
    mask.delete();
    mask = refined;
  }
  const labels = new cv.Mat();
  const stats = new cv.Mat();
  const centroids = new cv.Mat();
  const n = cv.connectedComponentsWithStats(mask, labels, stats, centroids, 8, cv.CV_32S);
  const relabel = new Int32Array(n);
  for (let lbl = 1, k = 0; lbl < n; lbl++) {
    if (stats.data32S[lbl * 5 + cv.CC_STAT_AREA] >= p.minAreaPx) relabel[lbl] = ++k;
  }
  const lab = labels.data32S;
  for (let i = 0; i < lab.length; i++) lab[i] = relabel[lab[i]];
  [mask, stats, centroids].forEach((m) => m.delete());
  return { labels, diff, band };
}
