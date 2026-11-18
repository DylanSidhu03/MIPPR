// Part 2: browser port of pipeline/mippr/segmentation/edges.py.
// Hysteresis threshold, hole filling and the half-maximum edge rule, whatever the background.
// Masks are CV_8UC1 Mats holding 0/1, difference maps CV_32FC1 Mats; every returned Mat is the caller's to delete.

function ellipse(cv, grow) {
  return cv.getStructuringElement(cv.MORPH_ELLIPSE, new cv.Size(2 * grow + 1, 2 * grow + 1));
}

function morph(cv, op, src, kernel) {
  const dst = new cv.Mat();
  cv.morphologyEx(src, dst, op, kernel);
  return dst;
}

function components(cv, mask) {
  const labels = new cv.Mat();
  const n = cv.connectedComponents(mask, labels, 8, cv.CV_32S);
  return [n, labels];
}

/** Rows y0..y1-1 and columns x0..x1-1 of a one-channel Mat, as a new Mat. */
function crop(cv, mat, x0, y0, x1, y1) {
  const rect = new cv.Rect(x0, y0, x1 - x0, y1 - y0);
  const view = mat.roi(rect);
  const out = view.clone();
  view.delete();
  return out;
}

/**
 * Keep low-threshold regions that contain at least one high-threshold pixel.
 * Inside the line band only structures at least 3 px wide count, and a region needs a strong
 * pixel outside the band to be kept.
 */
export function hysteresis(cv, diff, low, high, band) {
  const d = diff.data32F;
  const inBand = band.data;
  const lo = Math.fround(low);
  const hi = Math.fround(high);
  const weak = new cv.Mat(diff.rows, diff.cols, cv.CV_8UC1);
  const wk = weak.data;
  for (let i = 0; i < d.length; i++) wk[i] = d[i] >= lo ? 1 : 0;
  const ones = cv.Mat.ones(3, 3, cv.CV_8UC1);
  const opened = morph(cv, cv.MORPH_OPEN, weak, ones);
  const op = opened.data;
  for (let i = 0; i < d.length; i++) if (inBand[i]) wk[i] = op[i];
  const [n, labels] = components(cv, weak);
  const lab = labels.data32S;
  const keep = new Uint8Array(n);
  for (let i = 0; i < d.length; i++) if (d[i] >= hi && !inBand[i]) keep[lab[i]] = 1;
  keep[0] = 0;
  for (let i = 0; i < d.length; i++) wk[i] = keep[lab[i]];
  [ones, opened, labels].forEach((m) => m.delete());
  return weak;
}

/** Fill holes so particles with see-through centres (film, foam) stay whole. */
export function fillHoles(cv, mask) {
  const contours = new cv.MatVector();
  const hierarchy = new cv.Mat();
  cv.findContours(mask, contours, hierarchy, cv.RETR_EXTERNAL, cv.CHAIN_APPROX_NONE);
  const filled = cv.Mat.zeros(mask.rows, mask.cols, cv.CV_8UC1);
  cv.drawContours(filled, contours, -1, new cv.Scalar(1), cv.FILLED);
  contours.delete();
  hierarchy.delete();
  return filled;
}

function median32(values) {
  values.sort();
  const m = values.length >> 1;
  return values.length % 2 ? values[m] : Math.fround(Math.fround(values[m - 1] + values[m]) / 2);
}

function percentile32(values, q) {
  values.sort();
  const pos = (q / 100) * (values.length - 1);
  const i = Math.floor(pos);
  const t = pos - i;
  const a = values[i];
  const b = values[Math.min(i + 1, values.length - 1)];
  return Math.fround(t >= 0.5 ? b - (b - a) * (1 - t) : a + (b - a) * t);
}

/**
 * Difference value at which this particle's edge is drawn: `fraction` of its contrast, the median
 * difference over the particle's interior (its outer `grow` px left out).
 */
export function edgeLevel(cv, region, diff, fraction = 0.5, grow = 2) {
  const kernel = ellipse(cv, grow);
  const core = morph(cv, cv.MORPH_ERODE, region, kernel);
  const d = diff.data32F;
  const inCore = [];
  const inRegion = [];
  for (let i = 0; i < d.length; i++) {
    if (core.data[i]) inCore.push(d[i]);
    if (region.data[i]) inRegion.push(d[i]);
  }
  kernel.delete();
  core.delete();
  const contrast = inCore.length >= 5 ? median32(Float32Array.from(inCore)) : percentile32(Float32Array.from(inRegion), 90);
  return fraction * contrast;
}

/**
 * Move each particle's edge to where the difference falls to `fraction` of its contrast.
 * Only the outer edge may move, and only the part overlapping the detection is kept.
 * Each particle is worked on in its bounding box plus a margin, which gives the same result as the whole image.
 */
export function refineEdges(cv, mask, diff, fraction, grow = 2) {
  const { rows: h, cols: w } = mask;
  const labels = new cv.Mat();
  const stats = new cv.Mat();
  const centroids = new cv.Mat();
  const n = cv.connectedComponentsWithStats(mask, labels, stats, centroids, 8, cv.CV_32S);
  const out = cv.Mat.zeros(h, w, cv.CV_8UC1);
  const kernel = ellipse(cv, grow);
  const pad = grow + 1;
  const st = stats.data32S;
  for (let lbl = 1; lbl < n; lbl++) {
    const s = st.subarray(lbl * 5, lbl * 5 + 5);
    const x0 = Math.max(0, s[cv.CC_STAT_LEFT] - pad);
    const y0 = Math.max(0, s[cv.CC_STAT_TOP] - pad);
    const x1 = Math.min(w, s[cv.CC_STAT_LEFT] + s[cv.CC_STAT_WIDTH] + pad);
    const y1 = Math.min(h, s[cv.CC_STAT_TOP] + s[cv.CC_STAT_HEIGHT] + pad);
    const lab = crop(cv, labels, x0, y0, x1, y1);
    const d = crop(cv, diff, x0, y0, x1, y1);
    const region = new cv.Mat(lab.rows, lab.cols, cv.CV_8UC1);
    const rg = region.data;
    lab.data32S.forEach((v, i) => { rg[i] = v === lbl ? 1 : 0; });
    const level = Math.fround(edgeLevel(cv, region, d, fraction, grow));
    const near = morph(cv, cv.MORPH_DILATE, region, kernel);
    const core = morph(cv, cv.MORPH_ERODE, region, kernel);
    const refined = near;
    const rf = refined.data;
    const dv = d.data32F;
    for (let i = 0; i < rf.length; i++) rf[i] = (rf[i] && dv[i] >= level) || core.data[i] ? 1 : 0;
    const [k, parts] = components(cv, refined);
    if (k > 1) {
      const overlap = new Int32Array(k);
      const pt = parts.data32S;
      for (let i = 0; i < pt.length; i++) if (rg[i]) overlap[pt[i]]++;
      overlap[0] = 0;
      let best = 0;
      for (let j = 1; j < k; j++) if (overlap[j] > overlap[best]) best = j;
      const o = out.data;
      for (let y = y0; y < y1; y++) {
        for (let x = x0; x < x1; x++) if (pt[(y - y0) * (x1 - x0) + x - x0] === best) o[y * w + x] = 1;
      }
    }
    [lab, d, region, near, core, parts].forEach((m) => m.delete());
  }
  [labels, stats, centroids, kernel].forEach((m) => m.delete());
  const filled = fillHoles(cv, out);
  out.delete();
  return filled;
}
