// Part 3: browser port of pipeline/mippr/measurement/geometry.py.
// Deterministic size, shape and colour measurements from particle masks, with the same keys and values
// as Python's measure(). Functions that need OpenCV.js take it as their first argument; the outline
// tracing (marching squares, ImageJ's traced perimeter) and the Feret calipers are plain JS.
import { edgeLevel } from "../segmentation/edges.js";
import { count, crop, externalContours, maskMat, morph, plain, toMat } from "../grids.js";
import { fiberMetrics } from "./fiber.js";
import { opacity } from "./opacity.js";
import { REACH_PX, sizeRange } from "./uncertainty.js";

const DEG = 180 / Math.PI;
const CORNERS = [[-0.5, -0.5], [0.5, -0.5], [0.5, 0.5], [-0.5, 0.5]];

/** cv.convexHull of the outer corners of the given pixels, as a CV_32FC2 Mat (the caller deletes it). */
function hullMatOfPixelCorners(cv, pts) {
  const corners = [];
  for (const [x, y] of pts) for (const [ox, oy] of CORNERS) corners.push(x + ox, y + oy);
  const src = cv.matFromArray(corners.length / 2, 1, cv.CV_32FC2, corners);
  const hull = new cv.Mat();
  cv.convexHull(src, hull, false, true);
  src.delete();
  return hull;
}

function matPoints(mat) {
  const out = [];
  for (let i = 0; i < mat.data32F.length; i += 2) out.push([mat.data32F[i], mat.data32F[i + 1]]);
  return out;
}

/**
 * [max Feret, min Feret, max Feret angle in degrees] of a convex polygon (array of [x, y]), in px.
 * ImageJ's convention: called on the hull of the pixels' outer corners. The one place to change for a
 * sub-pixel Feret.
 */
export function feret(hull) {
  const n = hull.length;
  let best = -1, bi = 0, bj = 0;
  for (let i = 0; i < n; i++) {
    for (let j = 0; j < n; j++) {
      const dx = hull[i][0] - hull[j][0], dy = hull[i][1] - hull[j][1];
      const d = Math.sqrt(dx * dx + dy * dy);
      if (d > best) [best, bi, bj] = [d, i, j];
    }
  }
  let [a, b] = [hull[bi], hull[bj]];
  if (a[0] > b[0]) [a, b] = [b, a];
  const angle = pyMod(Math.atan2(-(b[1] - a[1]), b[0] - a[0]) * DEG, 180);
  let minWidth = Infinity;
  for (let k = 0; k < n; k++) {
    const ex = hull[(k + 1) % n][0] - hull[k][0], ey = hull[(k + 1) % n][1] - hull[k][1];
    const len = Math.hypot(ex, ey);
    if (!(len > 0)) continue;
    const nx = -ey / len, ny = ex / len;
    let lo = Infinity, hi = -Infinity;
    for (const [x, y] of hull) {
      const p = x * nx + y * ny;
      if (p < lo) lo = p;
      if (p > hi) hi = p;
    }
    minWidth = Math.min(minWidth, hi - lo);
  }
  return [best, minWidth, angle];
}

function pyMod(a, b) {
  const m = a % b;
  return m && m < 0 !== b < 0 ? m + b : m === 0 ? 0 : m;
}

/** [max Feret, min Feret] in px of a 0/1 grid, over all its external contours. */
export function feretPx(cv, mask) {
  const hull = hullMatOfPixelCorners(cv, externalContours(cv, mask).flat());
  const [fMax, fMin] = feret(matPoints(hull));
  hull.delete();
  return [fMax, fMin];
}

/**
 * Iso-lines of `field` (row-major, height x width) at `level`: skimage.measure.find_contours with its
 * defaults (low values fully connected), the same segments and the same assembly order. Each contour
 * is an array of [row, col].
 */
export function findContours(field, width, height, level) {
  const frac = (a, b) => (b === a ? 0 : (level - a) / (b - a));
  const segments = [];
  for (let r0 = 0; r0 < height - 1; r0++) {
    for (let c0 = 0; c0 < width - 1; c0++) {
      const r1 = r0 + 1, c1 = c0 + 1;
      const ul = field[r0 * width + c0], ur = field[r0 * width + c1];
      const ll = field[r1 * width + c0], lr = field[r1 * width + c1];
      if (Number.isNaN(ul) || Number.isNaN(ur) || Number.isNaN(ll) || Number.isNaN(lr)) continue;
      const sq = (ul > level) + 2 * (ur > level) + 4 * (ll > level) + 8 * (lr > level);
      if (sq === 0 || sq === 15) continue;
      const top = [r0, c0 + frac(ul, ur)];
      const bottom = [r1, c0 + frac(ll, lr)];
      const left = [r0 + frac(ul, ll), c0];
      const right = [r0 + frac(ur, lr), c1];
      if (sq === 1) segments.push([top, left]);
      else if (sq === 2) segments.push([right, top]);
      else if (sq === 3) segments.push([right, left]);
      else if (sq === 4) segments.push([left, bottom]);
      else if (sq === 5) segments.push([top, bottom]);
      else if (sq === 6) segments.push([right, top], [left, bottom]);
      else if (sq === 7) segments.push([right, bottom]);
      else if (sq === 8) segments.push([bottom, right]);
      else if (sq === 9) segments.push([top, left], [bottom, right]);
      else if (sq === 10) segments.push([bottom, top]);
      else if (sq === 11) segments.push([bottom, left]);
      else if (sq === 12) segments.push([left, right]);
      else if (sq === 13) segments.push([top, right]);
      else segments.push([left, top]);
    }
  }
  return assembleContours(segments);
}

// skimage's _assemble_contours. A contour is {head: reversed front part, tail: back part, num}.
function assembleContours(segments) {
  const key = (p) => `${p[0]},${p[1]}`;
  const first = (c) => (c.head.length ? c.head[c.head.length - 1] : c.tail[0]);
  const last = (c) => (c.tail.length ? c.tail[c.tail.length - 1] : c.head[0]);
  const items = (c) => c.head.slice().reverse().concat(c.tail);
  const contours = new Map(), starts = new Map(), ends = new Map();
  const pop = (m, k) => {
    const v = m.get(k);
    m.delete(k);
    return v;
  };
  let index = 0;
  for (const [from, to] of segments) {
    if (from[0] === to[0] && from[1] === to[1]) continue;
    const tail = pop(starts, key(to));
    const head = pop(ends, key(from));
    if (tail && head) {
      if (tail === head) {
        head.tail.push(to);
      } else if (tail.num > head.num) {
        head.tail.push(...items(tail));
        contours.delete(tail.num);
        starts.set(key(first(head)), head);
        ends.set(key(last(head)), head);
      } else {
        starts.delete(key(first(head)));
        tail.head.push(...items(head).reverse());
        contours.delete(head.num);
        starts.set(key(first(tail)), tail);
        ends.set(key(last(tail)), tail);
      }
    } else if (!tail && !head) {
      const c = { head: [], tail: [from, to], num: index++ };
      contours.set(c.num, c);
      starts.set(key(from), c);
      ends.set(key(to), c);
    } else if (!head) {
      tail.head.push(from);
      starts.set(key(from), tail);
    } else {
      head.tail.push(to);
      ends.set(key(to), head);
    }
  }
  return [...contours.values()].map(items);
}

/**
 * Sub-pixel outline (array of [x, y]) of one particle: the iso-line of the difference map at the
 * particle's edge level (or of the mask itself without one), traced near the particle only.
 * `mask` and `diff` are grids of the same window, whose top-left is at (ox, oy) in the image.
 */
export function subpixelOutline(cv, mask, diff = null, level = null, pad = 4, ox = 0, oy = 0) {
  let ymin = Infinity, ymax = -1, xmin = Infinity, xmax = -1;
  for (let y = 0; y < mask.height; y++) {
    for (let x = 0; x < mask.width; x++) {
      if (!mask.data[y * mask.width + x]) continue;
      if (y < ymin) ymin = y;
      if (y > ymax) ymax = y;
      if (x < xmin) xmin = x;
      if (x > xmax) xmax = x;
    }
  }
  const y0 = Math.max(0, ymin - pad), x0 = Math.max(0, xmin - pad);
  const y1 = Math.min(mask.height, ymax + pad + 1), x1 = Math.min(mask.width, xmax + pad + 1);
  const m = crop(mask, x0, y0, x1, y1);
  const w = m.width, h = m.height;
  const field = new Float64Array((w + 2) * (h + 2));
  const near = diff ? morph(cv, "dilate", m, 5) : null;
  const inner = diff ? morph(cv, "erode", m, 3) : null;
  if (!diff) level = 0.5;
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const i = y * w + x;
      let v;
      if (!diff) v = m.data[i];
      else {
        v = near.data[i] ? diff.data[(y0 + y) * diff.width + x0 + x] : 0;
        if (inner.data[i]) v = Math.max(v, 2 * level);
      }
      field[(y + 1) * (w + 2) + x + 1] = v;
    }
  }
  let line = [];
  for (const c of findContours(field, w + 2, h + 2, level)) if (c.length > line.length) line = c;
  return line.map(([r, c]) => [c - 1 + (x0 + ox), r - 1 + (y0 + oy)]);
}

/** Area of the convex hull of float points [[x, y]], computed on float32 like cv2.convexHull(pts.astype(np.float32)). */
function convexArea32(cv, pts) {
  const m = cv.matFromArray(pts.length, 1, cv.CV_32FC2, pts.flat());
  const hull = new cv.Mat();
  cv.convexHull(m, hull, false, true);
  const a = cv.contourArea(hull);
  m.delete();
  hull.delete();
  return a;
}

function polygonLengthArea(pts) {
  const n = pts.length;
  let length = 0, sxy = 0, syx = 0;
  for (let i = 0; i < n; i++) {
    const [x, y] = pts[i];
    const [xn, yn] = pts[(i + 1) % n];
    length += Math.hypot(xn - x, yn - y);
    sxy += x * yn;
    syx += y * xn;
  }
  return [length, 0.5 * Math.abs(sxy - syx)];
}

/**
 * Vertices (integer pixel-corner coordinates) of the outer pixel-edge boundary, in order: only the
 * points where the boundary turns, as in ImageJ's traced polygons.
 */
function crackVertices(mask) {
  const W = mask.width + 2, H = mask.height + 2;
  const inside = (px, py) =>
    px >= 1 && py >= 1 && px <= mask.width && py <= mask.height && mask.data[(py - 1) * mask.width + px - 1] > 0;
  let start = null;
  for (let y = 0; y < H && !start; y++) for (let x = 0; x < W && !start; x++) if (inside(x, y)) start = [x, y];
  let [x, y] = start;
  let d = [1, 0];
  const pts = [[x, y]];
  for (;;) {
    const [dx, dy] = d;
    let left, right;
    if (dx === 1) [left, right] = [inside(x, y - 1), inside(x, y)];
    else if (dy === 1) [left, right] = [inside(x, y), inside(x - 1, y)];
    else if (dx === -1) [left, right] = [inside(x - 1, y), inside(x - 1, y - 1)];
    else [left, right] = [inside(x - 1, y - 1), inside(x, y - 1)];
    const nd = left ? [dy, -dx] : right ? d : [-dy, dx];
    if (nd[0] !== d[0] || nd[1] !== d[1]) {
      pts.push([x, y]);
      d = nd;
    }
    x += d[0];
    y += d[1];
    if (x === start[0] && y === start[1]) break;
  }
  const p = pts.length > 1 && pts[0][0] === pts[1][0] && pts[0][1] === pts[1][1] ? pts.slice(1) : pts;
  const n = p.length;
  const keep = [];
  for (let i = 0; i < n; i++) {
    const a = p[(i - 1 + n) % n], b = p[i], c = p[(i + 1) % n];
    if ((b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0]) !== 0) keep.push([b[0] - 1, b[1] - 1]);
  }
  return keep;
}

/** Perimeter as ImageJ computes it for traced particles (PolygonRoi.getTracedPerimeter). */
export function perimeterImageJ(mask) {
  const pts = crackVertices(mask);
  const n = pts.length;
  if (n < 4) return 0;
  let sumdx = 0, sumdy = 0, nCorners = 0;
  let dx1 = pts[0][0] - pts[n - 1][0], dy1 = pts[0][1] - pts[n - 1][1];
  let side1 = Math.abs(dx1) + Math.abs(dy1);
  let corner = false;
  for (let i = 0; i < n; i++) {
    const dx2 = pts[(i + 1) % n][0] - pts[i][0], dy2 = pts[(i + 1) % n][1] - pts[i][1];
    sumdx += Math.abs(dx1);
    sumdy += Math.abs(dy1);
    const side2 = Math.abs(dx2) + Math.abs(dy2);
    if (side1 > 1 || !corner) {
      corner = true;
      nCorners++;
    } else corner = false;
    [dx1, dy1, side1] = [dx2, dy2, side2];
  }
  return sumdx + sumdy - nCorners * (2 - Math.SQRT2);
}

/**
 * (major, minor) axis lengths in px of ImageJ's fitted ellipse (ij/process/EllipseFitter.java): the ellipse
 * with the particle's second moments (each pixel a unit square, hence the 1/12 terms) and its area.
 */
export function ellipseImageJ(mask) {
  const { width: w, data } = mask;
  let n = 0, sx = 0, sy = 0;
  for (let i = 0; i < data.length; i++) if (data[i]) (n++, (sx += i % w), (sy += Math.floor(i / w)));
  const xm = sx / n, ym = sy / n;
  let sxx = 0, syy = 0, sxy = 0;
  for (let i = 0; i < data.length; i++) {
    if (!data[i]) continue;
    const dx = (i % w) - xm, dy = Math.floor(i / w) - ym;
    sxx += dx * dx, syy += dy * dy, sxy += dx * dy;
  }
  const u20 = sxx / n + 0.08333333, u02 = syy / n + 0.08333333, u11 = sxy / n;
  const m4 = Math.max(4.0 * Math.abs(u02 * u20 - u11 * u11), 0.000001);
  let a11 = u02 / m4, a22 = u20 / m4;
  const a12 = u11 / m4;
  let tmp = a11 - a22;
  if (tmp === 0) tmp = 0.000001;
  let theta = 0.5 * Math.atan((2.0 * a12) / tmp);
  if (theta < 0) theta += Math.PI / 2;
  if (a12 > 0) theta += Math.PI / 2;
  else if (a12 === 0) {
    if (a22 > a11) (theta = 0), ([a11, a22] = [a22, a11]);
    else if (a11 !== a22) theta = Math.PI / 2;
  }
  tmp = Math.sin(theta);
  if (tmp === 0) tmp = 0.000001;
  const z = (a12 * Math.cos(theta)) / tmp;
  let major = Math.sqrt(1.0 / Math.abs(a22 + z)), minor = Math.sqrt(1.0 / Math.abs(a11 - z));
  const scale = Math.sqrt(n / (Math.PI * major * minor)); // equal areas
  major *= scale * 2.0, minor *= scale * 2.0;
  return major >= minor ? [major, minor] : [minor, major];
}

function meanSd(vals) {
  let s = 0;
  for (const v of vals) s += v;
  const mean = s / vals.length;
  let q = 0;
  for (const v of vals) q += (v - mean) * (v - mean);
  return [mean, Math.sqrt(q / vals.length)];
}

/**
 * Mean and standard deviation of RGB, HSV and Lab inside the mask (one edge pixel removed when enough
 * pixels remain). `img` is an 8-bit BGR grid of the same window as `mask`.
 */
export function colorStats(cv, img, mask) {
  const inner = morph(cv, "erode", mask, 3);
  const m = count(inner) >= 4 ? inner : mask;
  const bgr = [];
  for (let i = 0; i < m.data.length; i++) if (m.data[i]) bgr.push(img.data[3 * i], img.data[3 * i + 1], img.data[3 * i + 2]);
  const n = bgr.length / 3;
  const src = new cv.Mat(n, 1, cv.CV_8UC3);
  src.data.set(bgr);
  const hsvMat = new cv.Mat(), labMat = new cv.Mat();
  cv.cvtColor(src, hsvMat, cv.COLOR_BGR2HSV_FULL);
  cv.cvtColor(src, labMat, cv.COLOR_BGR2Lab);
  const chan = (data, c, f = (v) => v) => Array.from({ length: n }, (_, i) => f(data[3 * i + c]));
  const out = { color_px: n };
  const series = [
    ["R", chan(bgr, 2)], ["G", chan(bgr, 1)], ["B", chan(bgr, 0)],
    ["S", chan(hsvMat.data, 1)], ["V", chan(hsvMat.data, 2)],
    ["L", chan(labMat.data, 0, (v) => v * (100 / 255))], ["a", chan(labMat.data, 1, (v) => v - 128)],
    ["b", chan(labMat.data, 2, (v) => v - 128)],
  ];
  for (const [name, vals] of series) [out[`${name}_mean`], out[`${name}_sd`]] = meanSd(vals);
  const h = chan(hsvMat.data, 0, (v) => ((v * 360) / 256) * (Math.PI / 180));
  const s = meanSd(h.map(Math.sin))[0], c = meanSd(h.map(Math.cos))[0];
  out.H_mean = pyMod(Math.atan2(s, c) * DEG, 360);
  out.H_sd = Math.sqrt(Math.max(0, -2 * Math.log(Math.max(1e-12, Math.hypot(s, c))))) * DEG;
  src.delete();
  hsvMat.delete();
  labMat.delete();
  return out;
}

/**
 * One object per particle with geometry in um / um^2 and colour statistics, as Python's measure().
 *
 * `labels` is a CV_32S Mat (0 = background), `img` the 8-bit BGR image, `diff` the CV_32F difference
 * map from segmentation (or null). Options as in Python: `boxFn(cx, cy)`, `lineMask` (CV_8U),
 * `colorImg` (8-bit BGR, used for colour instead of `img`), `bgImg` (expected background, same colour
 * space, any depth) and `minWidthPx`. Plain grids {width, height, channels, data} work in place of Mats.
 *
 * `colorClasses(img, mask, opacity)` gives the colour-class fields (color/rules.js); it is called with a
 * window of the colour image (8-bit BGR Mat) and the particle's 0/1 CV_8U mask of the same window, and
 * returns {label, confidence, secondary, secondaryFraction} (or the same as an array). Without it those
 * fields are undefined.
 */
export function measure(cv, labels, img, umPerPx, diff = null, edgeFraction = 0.5, edgeMarginPx = 3, options = {}) {
  const { boxFn = null, lineMask = null, colorImg = null, bgImg = null, minWidthPx = 2.0, colorClasses = null } = options;
  const L = plain(labels);
  const D = plain(diff), C = plain(colorImg ?? img), B = plain(bgImg), Lm = plain(lineMask);
  const { width: w, height: h } = L;
  const stats = new Map();
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const l = L.data[y * w + x];
      if (l <= 0) continue;
      let s = stats.get(l);
      if (!s) stats.set(l, (s = { n: 0, sx: 0, sy: 0, x0: x, x1: x, y0: y, y1: y }));
      s.n++;
      s.sx += x;
      s.sy += y;
      if (x < s.x0) s.x0 = x;
      if (x > s.x1) s.x1 = x;
      s.y1 = y;
    }
  }
  const pad = REACH_PX + 2;
  const u = umPerPx, u2 = umPerPx ** 2;
  const rows = [];
  for (const lbl of [...stats.keys()].sort((a, b) => a - b)) {
    const s = stats.get(lbl);
    const ox = Math.max(0, s.x0 - pad), oy = Math.max(0, s.y0 - pad);
    const ex = Math.min(w, s.x1 + pad + 1), ey = Math.min(h, s.y1 + pad + 1);
    const lab = crop(L, ox, oy, ex, ey);
    const mask = { width: lab.width, height: lab.height, channels: 1, data: Uint8Array.from(lab.data, (v) => v === lbl) };
    const d = D && crop(D, ox, oy, ex, ey);
    const areaPx = s.n;

    const contours = externalContours(cv, mask, ox, oy);
    const contour = contours.reduce((a, b) => (b.length > a.length ? b : a));
    const hullMat = hullMatOfPixelCorners(cv, contour);
    const [fMax, fMin, fAngle] = feret(matPoints(hullMat));
    const level = d ? edgeLevel(cv, mask, d, edgeFraction) : null;
    const outline = subpixelOutline(cv, mask, d, level, 4, ox, oy);
    const [perim, outlineArea] = polygonLengthArea(outline);
    const outlineHull = convexArea32(cv, outline);
    const perimIJ = perimeterImageJ(mask);
    const [major, minor] = ellipseImageJ(mask);
    const convexArea = cv.contourArea(hullMat);
    const convexPerim = cv.arcLength(hullMat, true);
    const rect = cv.minAreaRect(hullMat);
    hullMat.delete();
    const cx = s.sx / areaPx, cy = s.sy / areaPx;
    const { x0, x1, y0, y1 } = s;
    const [rw, rh] = [rect.size.width, rect.size.height];
    const row = {
      particle: lbl,
      box: boxFn ? boxFn(cx, cy) : "",
      x_um: cx * u,
      y_um: cy * u,
      area_um2: areaPx * u2,
      area_px: areaPx,
      perimeter_um: perimIJ * u, // ImageJ's traced perimeter
      perimeter_subpixel_um: perim * u,
      convex_area_um2: convexArea * u2,
      convex_perimeter_um: convexPerim * u,
      feret_max_um: fMax * u,
      feret_min_um: fMin * u,
      feret_angle_deg: fAngle,
      ced_um: 2 * Math.sqrt(areaPx / Math.PI) * u,
      bbox_width_um: (x1 - x0 + 1) * u,
      bbox_height_um: (y1 - y0 + 1) * u,
      min_rect_length_um: Math.max(rw, rh) * u,
      min_rect_width_um: Math.min(rw, rh) * u,
      major_um: major * u, // ImageJ's fitted ellipse
      minor_um: minor * u,
      aspect_ratio: minor > 0 ? major / minor : NaN, // ImageJ AR
      roundness: major > 0 ? (4 * areaPx) / (Math.PI * major ** 2) : NaN, // ImageJ Round
      feret_ratio: fMin > 0 ? fMax / fMin : NaN, // length:width, used by the rules
      circularity: perimIJ > 0 ? Math.min(1, (4 * Math.PI * areaPx) / perimIJ ** 2) : NaN, // ImageJ Circ.
      circularity_subpixel: perim > 0 ? Math.min(1, (4 * Math.PI * outlineArea) / perim ** 2) : NaN,
      solidity: convexArea > 0 ? Math.min(1, areaPx / convexArea) : NaN,
      // Solidity of the sub-pixel outline (about 1.0 for a round particle at any size); the pellet rule uses it.
      solidity_subpixel: outlineHull > 0 ? Math.min(1, outlineArea / outlineHull) : NaN,
    };
    const cimg = crop(C, ox, oy, ex, ey);
    Object.assign(row, colorStats(cv, cimg, mask));
    const [flPx, fwPx, uniform] = fiberMetrics(mask);
    row.fiber_length_um = flPx * u;
    row.fiber_width_um = fwPx * u;
    row.fiber_uniform = uniform;
    row.width_unresolved = Math.min(uniform ? fwPx : fMin, fMin) < minWidthPx;
    row.opacity = B && !row.width_unresolved ? opacity(cv, cimg, crop(B, ox, oy, ex, ey), mask) : null;
    if (colorClasses) {
      const imgMat = toMat(cv, cimg), mMat = maskMat(cv, mask);
      const r = colorClasses(imgMat, mMat, row.opacity);
      [row.color_label, row.color_confidence, row.color_secondary, row.color_secondary_fraction] = Array.isArray(r)
        ? r
        : [r.label, r.confidence, r.secondary, r.secondaryFraction];
      imgMat.delete();
      mMat.delete();
    } else {
      row.color_label = row.color_confidence = row.color_secondary = row.color_secondary_fraction = undefined;
    }
    row._contrast = level !== null ? level / edgeFraction : NaN;
    if (d) {
      for (const [k, v] of Object.entries(sizeRange(cv, mask, d, (m) => feretPx(cv, m), edgeFraction))) {
        row[k.replace("_px_", "_um_")] = v * u;
      }
    }
    let touches = false;
    if (Lm) for (let i = 0; i < mask.data.length && !touches; i++) {
      touches = mask.data[i] && Lm.data[(oy + Math.floor(i / mask.width)) * w + ox + (i % mask.width)] > 0;
    }
    row._touches_line = Boolean(touches);
    const e = edgeMarginPx;
    row._touches_edge = x0 < e || y0 < e || x1 >= w - e || y1 >= h - e;
    row._px = { cx, cy, x: x0, y: y0, w: x1 - x0 + 1, h: y1 - y0 + 1 };
    rows.push(row);
  }
  return rows;
}
