// Printer scale from the paper's edges: the JS twin of printer_scale in pipeline/mippr/capture/calibration.py.
//
// A printer set to "fit to page" shrinks the whole sheet, markers included, so the markers make every
// size come out too large by the same factor. Paper is made to a standard size whatever the printer, so when all four paper
// edges are in the photo, the paper is a ruler that doesn't depend on the printer. Width and height
// together also say which paper was used (Letter and A4 differ in shape by 9%).
import { PAPERS, pyRound, toGray } from "./sheet.js";
import { Problem } from "./quality.js";

export const PRINTER_SCALE_TOL = 0.01; // correct the scale when the printer changed it by more than 1%
const PAPER_SEARCH_MM = 25.0; // how far outside the nominal paper edge to look (Letter fitted onto A4: 13 mm)
const PAPER_INSIDE_MM = 5.0; // and how far inside
const EDGE_PPM = 4.0; // px per mm of the edge search
const MIN_EDGE_STEP = 25.0; // paper at least this many grey levels brighter than what it lies on
const MAX_EDGE_SPREAD_MM = 0.3; // edge positions along one side agree this well (median absolute deviation)
const MIN_EDGE_SHARE = 0.25; // and are found along at least this share of the side
const MAX_LENS_RMS_PX = 2.0; // skip the estimate if the lens model fits worse than this

const median = (a) => {
  const s = Float64Array.from(a).sort();
  const n = s.length;
  return n % 2 ? s[(n - 1) / 2] : (s[n / 2 - 1] + s[n / 2]) / 2;
};

/** Undistorted positions u = c + (p - c)(1 + q r^2) of photo points `pts` ([[x, y]]). */
function undistort(pts, q, c, n) {
  return pts.map(([x, y]) => {
    const dx = x - c[0], dy = y - c[1];
    const f = 1 + q * ((dx / n) ** 2 + (dy / n) ** 2);
    return [c[0] + dx * f, c[1] + dy * f];
  });
}

function applyH(H, [x, y]) {
  const w = H[6] * x + H[7] * y + H[8];
  return [(H[0] * x + H[1] * y + H[2]) / w, (H[3] * x + H[4] * y + H[5]) / w];
}

/**
 * {q, H, rms}: radial lens distortion and the sheet mm -> undistorted photo px homography, fitted to the
 * grid crossings and markers (lens_model in calibration.py).
 */
export function lensModel(cv, sheet, img) {
  const w = img.cols, h = img.rows;
  const c = [w / 2, h / 2], n = w / 2;
  const lay = sheet.layout;
  const [gx, gy] = lay.gridOriginMm, b = lay.boxMm;
  let mm = [], px = [];
  for (let j = 0; j <= lay.rows; j++) {
    for (let i = 0; i <= lay.cols; i++) mm.push([gx + i * b, gy + j * b]), px.push(sheet.crossings[j][i]);
  }
  const expected = lay.markerCornersMm();
  for (const k of Object.keys(sheet.markers).map(Number).sort((a, z) => a - z)) {
    if (!(k in expected)) continue;
    expected[k].forEach((p, i) => (mm.push(p), px.push(sheet.markers[k][i])));
  }
  const keep = px.map((p) => Number.isFinite(p[0]) && Number.isFinite(p[1]));
  mm = mm.filter((_, i) => keep[i]);
  px = px.filter((_, i) => keep[i]);

  const fit = (q) => {
    const u = undistort(px, q, c, n);
    const src = cv.matFromArray(mm.length, 1, cv.CV_64FC2, mm.flat());
    const dst = cv.matFromArray(u.length, 1, cv.CV_64FC2, u.flat());
    const Hm = cv.findHomography(src, dst, 0);
    const H = Array.from(Hm.data64F);
    [src, dst, Hm].forEach((m) => m.delete());
    let s = 0;
    const errs = mm.map((p, i) => {
      const [x, y] = applyH(H, p);
      const e = Math.hypot(x - u[i][0], y - u[i][1]);
      s += e * e;
      return e;
    });
    return { rms: Math.sqrt(s / mm.length), H, errs };
  };
  const search = () => {
    let lo = -0.25, hi = 0.25;
    const g = (Math.sqrt(5) - 1) / 2;
    let a = hi - g * (hi - lo), d = lo + g * (hi - lo);
    let fa = fit(a).rms, fd = fit(d).rms;
    for (let it = 0; it < 40; it++) {
      if (fa < fd) {
        [hi, d, fd] = [d, a, fa];
        a = hi - g * (hi - lo);
        fa = fit(a).rms;
      } else {
        [lo, a, fa] = [a, d, fd];
        d = lo + g * (hi - lo);
        fd = fit(d).rms;
      }
    }
    return (lo + hi) / 2;
  };
  let q = search();
  // Drop points far off the first fit (e.g. a checkerboard corner that didn't converge) and fit again.
  const { errs } = fit(q);
  const limit = Math.max(1.0, 3 * median(errs));
  const good = errs.map((e) => e <= limit);
  const nGood = good.filter(Boolean).length;
  if (nGood >= 8 && nGood < good.length) {
    mm = mm.filter((_, i) => good[i]);
    px = px.filter((_, i) => good[i]);
    q = search();
  }
  const { rms, H } = fit(q);
  return { q, H, rms };
}

/** Sub-pixel position of the strongest step in one profile (NaN outside the photo), or NaN (_edge_positions). */
function edgePosition(prof, rising, minDarkPx = 4) {
  const n = prof.length;
  const p = new Float64Array(n - 2);
  for (let i = 0; i < n - 2; i++) p[i] = (prof[i] + 2 * prof[i + 1] + prof[i + 2]) / 4;
  const g = new Float64Array(p.length - 2);
  for (let i = 0; i < g.length; i++) g[i] = (p[i + 2] - p[i]) * (rising ? 1 : -1);
  let i = -1;
  for (let k = 0; k < g.length; k++) if (Number.isFinite(g[k]) && (i < 0 || g[k] > g[i])) i = k;
  if (i < 0) return NaN;
  const finite = (a) => Array.from(a).filter(Number.isFinite);
  const before = finite(p.subarray(0, i + 1)), after = finite(p.subarray(i + 2));
  const [dark, bright] = rising ? [before, after] : [after, before];
  if (dark.length < minDarkPx || bright.length < minDarkPx || median(bright) - median(dark) < MIN_EDGE_STEP) return NaN;
  let d = 0;
  if (i > 0 && i < g.length - 1 && Number.isFinite(g[i - 1]) && Number.isFinite(g[i + 1])) {
    const den = g[i - 1] - 2 * g[i] + g[i + 1];
    d = den !== 0 ? (0.5 * (g[i - 1] - g[i + 1])) / den : 0;
  }
  return i + 2 + d;
}

/** {left, right, top, bottom}: the paper's edges in sheet mm (null where not found); paper_edges in calibration.py. */
export function paperEdges(cv, sheet, img) {
  const sides = ["left", "right", "top", "bottom"];
  const lay = sheet.layout;
  const [W, H] = lay.sizeMm;
  const E = PAPER_SEARCH_MM, I = PAPER_INSIDE_MM, k = EDGE_PPM;
  const { q, H: Hm, rms } = lensModel(cv, sheet, img);
  if (rms > MAX_LENS_RMS_PX) return Object.fromEntries(sides.map((s) => [s, null]));
  const gray = toGray(cv, img);
  const pw = gray.cols, ph = gray.rows;
  const c = [pw / 2, ph / 2], n = pw / 2;
  const cw = Math.round((W + 2 * E) * k), ch = Math.round((H + 2 * E) * k);
  const mx = new cv.Mat(ch, cw, cv.CV_32FC1), my = new cv.Mat(ch, cw, cv.CV_32FC1);
  const valid = new Uint8Array(cw * ch);
  for (let y = 0; y < ch; y++) {
    for (let x = 0; x < cw; x++) {
      const u = applyH(Hm, [(x + 0.5) / k - E, (y + 0.5) / k - E]);
      let p = u;
      for (let it = 0; it < 8; it++) { // invert u = c + (p - c)(1 + q r^2) for p
        const f = 1 + q * (((p[0] - c[0]) / n) ** 2 + ((p[1] - c[1]) / n) ** 2);
        p = [c[0] + (u[0] - c[0]) / f, c[1] + (u[1] - c[1]) / f];
      }
      const o = y * cw + x;
      const fx = Math.fround(p[0]), fy = Math.fround(p[1]);
      mx.data32F[o] = fx;
      my.data32F[o] = fy;
      valid[o] = fx >= 1 && fy >= 1 && fx < pw - 1 && fy < ph - 1 ? 1 : 0;
    }
  }
  const canvas = new cv.Mat();
  cv.remap(gray, canvas, mx, my, cv.INTER_LINEAR, cv.BORDER_CONSTANT, new cv.Scalar(0));
  [gray, mx, my].forEach((m) => m.delete());
  const at = (x, y) => (valid[y * cw + x] ? canvas.data[y * cw + x] : NaN);
  const P = (v) => Math.round((v + E) * k); // sheet mm -> canvas px (Python's round: half to even is irrelevant here)
  const clear = lay.marginMm + lay.markerMm + 4;
  const out = {};
  for (const side of sides) {
    const vertical = side === "left" || side === "right";
    const [a, b] = vertical ? [P(clear), P(H - clear)] : [P(clear), P(W - clear)];
    const [lo, hi] = side === "left" ? [P(-E), P(I)] : side === "right" ? [P(W - I), P(W + E)]
      : side === "top" ? [P(-E), P(I)] : [P(H - I), P(H + E)];
    const pos = [];
    for (let r = a; r < b; r++) {
      const prof = new Float64Array(hi - lo);
      for (let t = lo; t < hi; t++) prof[t - lo] = vertical ? at(t, r) : at(r, t);
      const v = edgePosition(prof, side === "left" || side === "top");
      if (Number.isFinite(v)) pos.push(v);
    }
    if (pos.length < MIN_EDGE_SHARE * (b - a)) {
      out[side] = null;
      continue;
    }
    const med = median(pos);
    if (median(pos.map((v) => Math.abs(v - med))) / k > MAX_EDGE_SPREAD_MM) {
      out[side] = null;
      continue;
    }
    out[side] = (lo + med + 0.5) / k - E;
  }
  canvas.delete();
  return out;
}

const round = pyRound; // Python's round(): half to even, as calibration.py
const g6 = (v) => String(Number(Number(v).toPrecision(6))); // Python's f"{v:g}" for ordinary values

/**
 * How the printer scaled the sheet: {scale, paper, scale_x, scale_y, edges_mm}. `scale` is printed size /
 * true size (0.97 = printed at 97%); null unless all four edges were found and width and height agree on
 * one paper size.
 */
export function printerScale(cv, sheet, img) {
  const edges = paperEdges(cv, sheet, img);
  const out = { scale: null, paper: null, scale_x: null, scale_y: null,
    edges_mm: Object.fromEntries(Object.entries(edges).map(([k, v]) => [k, v === null ? null : round(v, 2)])) };
  if (Object.values(edges).some((v) => v === null)) return out;
  const mw = edges.right - edges.left, mh = edges.bottom - edges.top;
  let best = null;
  for (const [paper, [pw, ph]] of Object.entries(PAPERS)) {
    const sx = pw / mw, sy = ph / mh;
    if (best === null || Math.abs(sx - sy) < Math.abs(best[1] - best[2])) best = [paper, sx, sy];
  }
  const [paper, sx, sy] = best;
  Object.assign(out, { paper, scale_x: round(sx, 4), scale_y: round(sy, 4) });
  if (Math.abs(sx - sy) <= 0.01) out.scale = round((sx + sy) / 2, 4);
  return out;
}

/** A Problem saying the printer scaled the sheet (and that sizes were corrected), or null. */
export function printerProblem(ps, lineMm = null) {
  const s = ps.scale;
  if (s === null || Math.abs(s - 1) <= PRINTER_SCALE_TOL) return null;
  const pct = pyRound(100 * s, 0).toFixed(0); // f"{100 * s:.0f}" rounds half to even
  if (lineMm !== null && lineMm !== undefined) {
    return new Problem("printer_scaled", `The sheet looks printed at ${pct}% of its size (from the paper's edges), ` +
      `but the 100 mm line was entered as ${g6(lineMm)} mm; the entered length was used.`, s, PRINTER_SCALE_TOL);
  }
  return new Problem("printer_scaled", `The printer scaled the sheet to ${pct}% of its size. Sizes were corrected ` +
    "from the paper's edges; to avoid this, print at actual size (100%).", s, PRINTER_SCALE_TOL);
}
