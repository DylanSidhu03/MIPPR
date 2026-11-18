// Part 4: browser port of pipeline/mippr/color/rules.py.
// Each pixel goes into one of the 13 colour classes, then the particle gets its main colour, second colour and
// that colour's share. pixelClasses and labelFromLab are plain JS; colorClasses takes the OpenCV.js module as `cv`.
// Parity with the Python reference is checked by web/tests/export.test.mjs.

export const COLOR_RULES_VERSION = "0.1-provisional";

export const COLOR_CLASSES = Object.freeze(["clear", "white", "black", "grey", "blue", "green", "red", "yellow",
  "orange", "brown", "pink", "purple", "multicolor"]);
export const PIXEL_CLASSES = Object.freeze(COLOR_CLASSES.slice(1, -1)); // clear and multicolor are particle-level
export const CHROMA_MIN = 12.0; // below this, a pixel is white, grey or black
export const WHITE_L = 80.0;
export const BLACK_L = 25.0;
export const MULTICOLOR_SHARE = 0.2; // decided in spec v0.1: a second colour covering >= 20%
export const CLEAR_OPACITY = 0.5;
export const MULTICOLOR_DELTA_E = 25.0;
// Neighbouring classes that shading, or a hue on a class boundary, produces on one particle: recorded as the second
// colour, but they don't make a particle multicolour.
export const SHADES = Object.freeze([["white", "grey"], ["grey", "black"], ["red", "pink"], ["red", "orange"],
  ["orange", "brown"], ["yellow", "brown"], ["orange", "yellow"], ["yellow", "green"], ["green", "blue"],
  ["blue", "purple"], ["purple", "pink"], ["red", "brown"], ["white", "yellow"], ["white", "pink"],
  ["grey", "brown"]].map((p) => Object.freeze(p)));

const shadeKeys = new Set(SHADES.map((p) => [...p].sort().join("|")));
const RAD2DEG = 180.0 / Math.PI; // as numpy.degrees

function isShade(a, b) {
  return shadeKeys.has([a, b].sort().join("|"));
}

/** Python's float `%` (numpy.remainder): the result takes the divisor's sign. */
function pyMod(x, m) {
  const r = x % m;
  return r && (r < 0) !== (m < 0) ? r + m : r;
}

function hypotKernel(ax, ay) {
  let h = Math.sqrt(ax * ax + ay * ay);
  let t1, t2;
  if (h <= 2.0 * ay) {
    const delta = h - ay;
    t1 = ax * (2.0 * delta - ax);
    t2 = (delta - 2.0 * (ax - ay)) * delta;
  } else {
    const delta = h - ax;
    t1 = 2.0 * delta * (ax - 2.0 * ay);
    t2 = (4.0 * delta - ay) * ay + delta * delta;
  }
  h -= (t1 + t2) / (2.0 * h);
  return h;
}

/** glibc's hypot (numpy.hypot in the Python reference), so pixels on the CHROMA_MIN edge fall the same way. */
function hypot(x, y) {
  x = Math.abs(x);
  y = Math.abs(y);
  if (!Number.isFinite(x) || !Number.isFinite(y)) return Math.hypot(x, y);
  const [ax, ay] = x < y ? [y, x] : [x, y];
  if (ax > 2 ** 511) return ay <= ax * 2 ** -54 ? ax + ay : hypotKernel(ax * 2 ** -600, ay * 2 ** -600) * 2 ** 600;
  if (ay < 2 ** -511) return ax >= ay * 2 ** 54 ? ax + ay : hypotKernel(ax * 2 ** 600, ay * 2 ** 600) * 2 ** -600;
  return ay <= ax * 2 ** -54 ? ax + ay : hypotKernel(ax, ay);
}

function pixelClass(L, a, b) {
  const C = hypot(a, b);
  if (C < CHROMA_MIN) return L >= WHITE_L ? "white" : L <= BLACK_L ? "black" : "grey";
  if (L <= BLACK_L * 0.6) return "black"; // very dark chromatic pixels read as black
  const h = pyMod(Math.atan2(b, a) * RAD2DEG, 360);
  if (h >= 345 || h < 40) return L > 65 ? "pink" : "red";
  if (h < 75) return L < 50 ? "brown" : "orange";
  if (h < 105) return L < 50 ? "brown" : "yellow";
  if (h < 200) return "green";
  if (h < 295) return "blue";
  return L > 70 ? "pink" : "purple";
}

/** Colour class name for each CIE Lab pixel; `lab` is flat [L0, a0, b0, L1, ...]. Provisional hue ranges. */
export function pixelClasses(lab) {
  const out = new Array(lab.length / 3);
  for (let i = 0; i < out.length; i++) out[i] = pixelClass(lab[3 * i], lab[3 * i + 1], lab[3 * i + 2]);
  return out;
}

function meanLab(lab, cls, name) {
  const s = [0, 0, 0];
  let n = 0;
  for (let i = 0; i < cls.length; i++) {
    if (name !== null && cls[i] !== name) continue;
    s[0] += lab[3 * i];
    s[1] += lab[3 * i + 1];
    s[2] += lab[3 * i + 2];
    n++;
  }
  return s.map((v) => v / n);
}

/**
 * The particle-level decision from its CIE Lab pixels (flat [L, a, b, ...]):
 * {label, confidence, secondary, secondaryFraction}. `opacity` is null when unknown.
 */
export function labelFromLab(lab, opacity = null) {
  const cls = pixelClasses(lab);
  const counts = new Map();
  for (const c of cls) counts.set(c, (counts.get(c) || 0) + 1);
  // Alphabetical, then by count (a stable sort), as numpy's unique + argsort on these few classes.
  const ranked = [...counts].sort((x, y) => (x[0] < y[0] ? -1 : 1)).sort((x, y) => y[1] - x[1]);
  const total = cls.length;
  const [main, mainCount] = ranked[0];
  const mainShare = mainCount / total;
  let [second, secondShare] = ["", 0.0];
  if (ranked.length > 1) [second, secondShare] = [ranked[1][0], ranked[1][1] / total];
  let [label, confidence] = [main, mainShare];
  if (second && secondShare >= MULTICOLOR_SHARE && !isShade(main, second)) {
    const m1 = meanLab(lab, cls, main);
    const m2 = meanLab(lab, cls, second);
    if (Math.sqrt((m1[0] - m2[0]) ** 2 + (m1[1] - m2[1]) ** 2 + (m1[2] - m2[2]) ** 2) >= MULTICOLOR_DELTA_E) {
      [label, confidence] = ["multicolor", mainShare + secondShare];
    }
  }
  const mean = meanLab(lab, cls, null);
  if (opacity !== null && opacity !== undefined && opacity < CLEAR_OPACITY && label !== "multicolor"
      && hypot(mean[1], mean[2]) < 2 * CHROMA_MIN) {
    [label, confidence] = ["clear", 1 - opacity];
  }
  return { label, confidence, secondary: second, secondaryFraction: secondShare };
}

/**
 * {label, confidence, secondary, secondaryFraction} for one particle.
 * `img` is a cv.Mat (3 channels BGR as in Python, 4 channels RGBA from a canvas); `mask` is a CV_8UC1 cv.Mat or an
 * array of rows * cols bytes, nonzero inside the particle. Pixels inside the outline (one edge pixel removed) are
 * classed after a 3 x 3 median filter.
 */
export function colorClasses(cv, img, mask, opacity = null) {
  const { rows, cols } = img;
  const m8 = mask instanceof cv.Mat ? mask : cv.matFromArray(rows, cols, cv.CV_8UC1, Array.from(mask));
  const bin = new cv.Mat();
  const inner = new cv.Mat();
  const kernel = cv.Mat.ones(3, 3, cv.CV_8U);
  const mats = [bin, inner, kernel];
  if (m8 !== mask) mats.push(m8);
  try {
    cv.threshold(m8, bin, 0, 1, cv.THRESH_BINARY);
    cv.erode(bin, inner, kernel, new cv.Point(-1, -1), 1, cv.BORDER_CONSTANT, cv.morphologyDefaultBorderValue());
    const m = (cv.countNonZero(inner) >= 4 ? inner : bin).data;
    let [x0, y0, x1, y1] = [cols, rows, -1, -1];
    for (let y = 0; y < rows; y++) {
      for (let x = 0; x < cols; x++) {
        if (!m[y * cols + x]) continue;
        if (x < x0) x0 = x;
        if (x > x1) x1 = x;
        if (y < y0) y0 = y;
        if (y > y1) y1 = y;
      }
    }
    if (x1 < 0) throw new Error("colorClasses: the mask is empty");
    const roi = img.roi(new cv.Rect(x0, y0, x1 - x0 + 1, y1 - y0 + 1));
    const crop = roi.clone();
    const blurred = new cv.Mat();
    const labImg = new cv.Mat();
    mats.push(roi, crop, blurred, labImg);
    cv.medianBlur(crop, blurred, 3);
    if (img.channels() === 4) {
      const rgb = new cv.Mat();
      mats.push(rgb);
      cv.cvtColor(blurred, rgb, cv.COLOR_RGBA2RGB);
      cv.cvtColor(rgb, labImg, cv.COLOR_RGB2Lab);
    } else {
      cv.cvtColor(blurred, labImg, cv.COLOR_BGR2Lab);
    }
    const w = x1 - x0 + 1;
    const d = labImg.data;
    const lab = [];
    for (let y = y0; y <= y1; y++) {
      for (let x = x0; x <= x1; x++) {
        if (!m[y * cols + x]) continue;
        const k = 3 * ((y - y0) * w + (x - x0));
        lab.push(d[k] * (100 / 255) - 0, d[k + 1] - 128, d[k + 2] - 128);
      }
    }
    return labelFromLab(lab, opacity);
  } finally {
    for (const mat of mats) mat.delete();
  }
}
