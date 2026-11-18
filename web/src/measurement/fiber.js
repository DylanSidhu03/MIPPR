// Part 3: browser port of pipeline/mippr/measurement/fiber.py.
// Length and width along a particle's centre line: the skeleton's longest path, smoothed, with the ends
// trimmed where the skeleton runs into corners and the true end length added back. The thinning is
// skimage's skeletonize (Zhang-Suen, same lookup table) and the path search reproduces SciPy's Dijkstra,
// so the results match the Python reference. Plain JS, no OpenCV.js.
import { crop } from "./_grid.js";

export const UNIFORM_MAX = 1.5;
export const END_TRIM = 0.9;

// skimage/morphology/_skeletonize_various_cy.pyx: 1 removed in the first pass, 2 in the second, 3 in both.
// prettier-ignore
const LUT = Uint8Array.from([
  0, 0, 0, 1, 0, 0, 1, 3, 0, 0, 3, 1, 1, 0, 1, 3, 0, 0, 0, 0, 0, 0, 0, 0, 2, 0, 2, 0, 3, 0, 3, 3,
  0, 0, 0, 0, 0, 0, 0, 0, 3, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 2, 0, 0, 0, 3, 0, 2, 2,
  0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
  2, 0, 0, 0, 0, 0, 0, 0, 2, 0, 0, 0, 2, 0, 0, 0, 3, 0, 0, 0, 0, 0, 0, 0, 3, 0, 0, 0, 3, 0, 2, 0,
  0, 0, 3, 1, 0, 0, 1, 3, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1,
  3, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 2, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
  2, 3, 1, 3, 0, 0, 1, 3, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
  2, 3, 0, 1, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 3, 3, 0, 1, 0, 0, 0, 0, 2, 2, 0, 0, 2, 0, 0, 0,
]);

/** skimage.morphology.skeletonize (2D, Zhang-Suen) of a 0/1 grid; returns a 0/1 Uint8Array of the same size. */
export function skeletonize(mask) {
  const W = mask.width + 2, H = mask.height + 2;
  const skel = new Uint8Array(W * H);
  for (let y = 0; y < mask.height; y++) {
    for (let x = 0; x < mask.width; x++) skel[(y + 1) * W + x + 1] = mask.data[y * mask.width + x] ? 1 : 0;
  }
  const cleaned = skel.slice();
  let removed = true;
  while (removed) {
    removed = false;
    for (let pass = 0; pass < 2; pass++) {
      for (let r = 1; r < H - 1; r++) {
        for (let c = 1; c < W - 1; c++) {
          const i = r * W + c;
          if (!skel[i]) continue;
          const nb = LUT[skel[i - W - 1] + 2 * skel[i - W] + 4 * skel[i - W + 1] + 8 * skel[i + 1] +
            16 * skel[i + W + 1] + 32 * skel[i + W] + 64 * skel[i + W - 1] + 128 * skel[i - 1]];
          if (nb === 3 || (nb === 1 && pass === 0) || (nb === 2 && pass === 1)) {
            cleaned[i] = 0;
            removed = true;
          }
        }
      }
      skel.set(cleaned);
    }
  }
  const out = new Uint8Array(mask.width * mask.height);
  for (let y = 0; y < mask.height; y++) out.set(skel.subarray((y + 1) * W + 1, (y + 1) * W + 1 + mask.width), y * mask.width);
  return out;
}

// Min-heap of [distance, index]; ties pop the larger index first, as SciPy's std::priority_queue of
// (-distance, index) pairs does, so the predecessors (and the path) are the same.
class Heap {
  constructor() {
    this.a = [];
  }
  static before(p, q) {
    return p[0] < q[0] || (p[0] === q[0] && p[1] > q[1]);
  }
  push(item) {
    const a = this.a;
    a.push(item);
    for (let i = a.length - 1; i > 0;) {
      const p = (i - 1) >> 1;
      if (!Heap.before(a[i], a[p])) break;
      [a[i], a[p]] = [a[p], a[i]];
      i = p;
    }
  }
  pop() {
    const a = this.a;
    const top = a[0];
    const end = a.pop();
    if (a.length) {
      a[0] = end;
      for (let i = 0; ;) {
        const l = 2 * i + 1, r = l + 1;
        let m = i;
        if (l < a.length && Heap.before(a[l], a[m])) m = l;
        if (r < a.length && Heap.before(a[r], a[m])) m = r;
        if (m === i) break;
        [a[i], a[m]] = [a[m], a[i]];
        i = m;
      }
    }
    return top;
  }
  get size() {
    return this.a.length;
  }
}

function dijkstra(nbrs, source) {
  const dist = new Float64Array(nbrs.length).fill(Infinity);
  const pred = new Int32Array(nbrs.length).fill(-9999);
  dist[source] = 0;
  const heap = new Heap();
  heap.push([0, source]);
  while (heap.size) {
    const [d, v] = heap.pop();
    if (dist[v] < d) continue;
    for (const [j, w] of nbrs[v]) {
      const next = d + w;
      if (dist[j] > next) {
        dist[j] = next;
        heap.push([next, j]);
        pred[j] = v;
      }
    }
  }
  return [dist, pred];
}

function argmaxFinite(dist) {
  let best = 0;
  for (let i = 1; i < dist.length; i++) {
    const v = Number.isFinite(dist[i]) ? dist[i] : -1;
    if (v > (Number.isFinite(dist[best]) ? dist[best] : -1)) best = i;
  }
  return best;
}

/** Pixel coordinates [[x, y], ...] along the longest shortest path through an 8-connected skeleton. */
export function longestPath(skel, width, height) {
  const xs = [], ys = [];
  const index = new Int32Array(width * height).fill(-1);
  for (let i = 0; i < skel.length; i++) {
    if (!skel[i]) continue;
    index[i] = xs.length;
    xs.push(i % width);
    ys.push(Math.floor(i / width));
  }
  const n = xs.length;
  if (n < 2) return xs.map((x, k) => [x, ys[k]]);
  const nbrs = Array.from({ length: n }, () => []);
  for (const [dy, dx] of [[0, 1], [1, 0], [1, 1], [1, -1]]) {
    const w = Math.hypot(dy, dx);
    for (let k = 0; k < n; k++) {
      const y2 = ys[k] + dy, x2 = xs[k] + dx;
      if (y2 < 0 || y2 >= height || x2 < 0 || x2 >= width) continue;
      const j = index[y2 * width + x2];
      if (j < 0) continue;
      nbrs[k].push([j, w]);
      nbrs[j].push([k, w]);
    }
  }
  const a = argmaxFinite(dijkstra(nbrs, 0)[0]);
  const [da, pred] = dijkstra(nbrs, a);
  const path = [argmaxFinite(da)];
  while (path[path.length - 1] !== a) path.push(pred[path[path.length - 1]]);
  return path.map((k) => [xs[k], ys[k]]);
}

/** Length of a pixel path after a moving-average smooth (window 7), the two ends kept in place. */
export function smoothLength(pts, window = 7) {
  const n = pts.length;
  if (n < 2) return 0;
  const k = Math.min(window, n % 2 ? n : n - 1);
  let sm = pts;
  if (k >= 3) {
    const pad = k >> 1;
    const ext = [...Array(pad).fill(pts[0]), ...pts, ...Array(pad).fill(pts[n - 1])];
    const kv = 1 / k;
    sm = pts.map((_, t) => {
      let sx = 0, sy = 0;
      for (let m = 0; m < k; m++) {
        sx += ext[t + m][0] * kv;
        sy += ext[t + m][1] * kv;
      }
      return [sx, sy];
    });
    sm[0] = pts[0];
    sm[n - 1] = pts[n - 1];
  }
  let length = 0;
  for (let i = 1; i < n; i++) length += Math.hypot(sm[i][0] - sm[i - 1][0], sm[i][1] - sm[i - 1][1]);
  return length;
}

function medianF32(vals) {
  const s = Float64Array.from(vals).sort();
  const n = s.length;
  return n % 2 ? s[(n - 1) / 2] : Math.fround(s[n / 2 - 1] + s[n / 2]) / 2;
}

const [HV, DIAG, LONG] = [1, 1.4, 2.1969].map(Math.fround);

/**
 * cv2.distanceTransform(mask, DIST_L2, 5): the 5 x 5 chamfer distance, in float32 as the Python wheels
 * compute it (through IPP). OpenCV.js has no IPP and rounds to 1/65536 px, so it isn't used here.
 */
export function distanceTransform(mask) {
  const { width: w, height: h } = mask;
  const W = w + 4;
  const t = new Float32Array(W * (h + 4)).fill(1e30);
  const f = Math.fround;
  for (let y = 2; y < h + 2; y++) {
    for (let x = 2; x < w + 2; x++) {
      const i = y * W + x;
      t[i] = !mask.data[(y - 2) * w + x - 2] ? 0 : Math.min(
        f(t[i - 2 * W - 1] + LONG), f(t[i - 2 * W + 1] + LONG), f(t[i - W - 2] + LONG), f(t[i - W - 1] + DIAG),
        f(t[i - W] + HV), f(t[i - W + 1] + DIAG), f(t[i - W + 2] + LONG), f(t[i - 1] + HV));
    }
  }
  const out = new Float32Array(w * h);
  for (let y = h + 1; y >= 2; y--) {
    for (let x = w + 1; x >= 2; x--) {
      const i = y * W + x;
      t[i] = Math.min(t[i],
        f(t[i + 2 * W + 1] + LONG), f(t[i + 2 * W - 1] + LONG), f(t[i + W + 2] + LONG), f(t[i + W + 1] + DIAG),
        f(t[i + W] + HV), f(t[i + W - 1] + DIAG), f(t[i + W - 2] + LONG), f(t[i + 1] + HV));
      out[(y - 2) * w + x - 2] = t[i];
    }
  }
  return out;
}

/** [lengthPx, meanWidthPx, uniform] along the centre line of a 0/1 grid, as fiber_metrics in Python. */
export function fiberMetrics(mask) {
  let area = 0, x0 = Infinity, x1 = -1, y0 = Infinity, y1 = -1;
  for (let y = 0; y < mask.height; y++) {
    for (let x = 0; x < mask.width; x++) {
      if (!mask.data[y * mask.width + x]) continue;
      area++;
      if (x < x0) x0 = x;
      if (x > x1) x1 = x;
      if (y < y0) y0 = y;
      if (y > y1) y1 = y;
    }
  }
  const inner = crop(mask, x0, y0, x1 + 1, y1 + 1);
  const W = inner.width + 2, H = inner.height + 2;
  const c = { width: W, height: H, channels: 1, data: new Uint8Array(W * H) };
  for (let y = 0; y < inner.height; y++) {
    for (let x = 0; x < inner.width; x++) c.data[(y + 1) * W + x + 1] = inner.data[y * inner.width + x] ? 1 : 0;
  }
  const dt = distanceTransform(c);

  const path = longestPath(skeletonize(c), W, H);
  let length;
  if (path.length < 3) {
    length = Math.max(W, H) - 2;
  } else {
    const d = path.map(([x, y]) => dt[y * W + x]);
    const half = medianF32(d);
    const n = path.length;
    const step = path.map((p, i) => (i ? Math.hypot(p[0] - path[i - 1][0], p[1] - path[i - 1][1]) : 0));
    const fromStart = new Float64Array(n), fromEnd = new Float64Array(n);
    for (let i = 0, s = 0; i < n; i++) fromStart[i] = s += step[i];
    for (let i = n - 1, s = 0; i >= 0; i--) fromEnd[i] = s += step[i];
    const keep = [];
    for (let i = 0; i < n; i++) {
      const endZone = fromStart[i] <= 1.5 * half || fromEnd[i] <= 1.5 * half;
      if (!endZone || d[i] >= END_TRIM * half) keep.push(i);
    }
    const ok = keep.length >= 2;
    const core = ok ? path.slice(keep[0], keep[keep.length - 1] + 1) : path;
    const trimmed = ok ? smoothLength(path) - smoothLength(core) : 0;
    length = smoothLength(core) + Math.min(2 * END_TRIM * half, trimmed + 2 * half);
  }
  const w = length > 0 ? area / length : 0;
  let dtMax = 0;
  for (const v of dt) if (v > dtMax) dtMax = v;
  return [length, w, w > 0 && 2 * dtMax <= UNIFORM_MAX * w];
}
