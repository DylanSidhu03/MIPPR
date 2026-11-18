// The two helpers of pipeline/mippr/segmentation/edges.py that measurement uses (edge_level, fill_holes).
// Kept here so this folder doesn't depend on the segmentation port.
import { count, maskMat, morph } from "./_grid.js";

/**
 * numpy's median and 90th percentile (method "linear"). A Float32Array is treated as numpy float32,
 * whose mean of the two middle values and interpolation are rounded to float32.
 */
function quantile(values, q, f32) {
  const r = f32 ? Math.fround : (v) => v;
  const s = Float64Array.from(values).sort();
  const n = s.length;
  if (q === 0.5) return n % 2 ? s[(n - 1) / 2] : r(s[n / 2 - 1] + s[n / 2]) / 2;
  const v = (n - 1) * q;
  if (v >= n - 1) return s[n - 1];
  const i = Math.floor(v);
  const t = v - i;
  const a = s[i], b = s[i + 1];
  const d = r(b - a);
  return t >= 0.5 ? r(b - r(d * r(1 - t))) : r(a + r(d * r(t)));
}

/**
 * Difference value at which this particle's edge is drawn: `fraction` of its contrast (the median over
 * its interior, the outer `grow` px left out). `region` is a 0/1 grid, `diff` a grid of the same size.
 */
export function edgeLevel(cv, region, diff, fraction = 0.5, grow = 2) {
  const core = morph(cv, "erode", region, 2 * grow + 1, "ellipse");
  const f32 = diff.data instanceof Float32Array;
  const pick = (m) => diff.data.filter((_, i) => m.data[i]);
  const contrast = count(core) >= 5 ? quantile(pick(core), 0.5, f32) : quantile(pick(region), 0.9, f32);
  return fraction * contrast;
}

/** Fill holes: every external contour drawn filled. */
export function fillHoles(cv, mask) {
  const src = maskMat(cv, mask);
  const contours = new cv.MatVector();
  const hierarchy = new cv.Mat();
  cv.findContours(src, contours, hierarchy, cv.RETR_EXTERNAL, cv.CHAIN_APPROX_NONE);
  const filled = cv.Mat.zeros(mask.height, mask.width, cv.CV_8UC1);
  cv.drawContours(filled, contours, -1, new cv.Scalar(1), cv.FILLED);
  const out = { width: mask.width, height: mask.height, channels: 1, data: Uint8Array.from(filled.data) };
  src.delete();
  contours.delete();
  hierarchy.delete();
  filled.delete();
  return out;
}
