// Part 3: browser port of pipeline/mippr/measurement/uncertainty.py.
// How much a particle's size depends on where its edge is drawn: the particle is outlined again with
// the edge at 40% and 60% of its contrast and its length and width measured each time.
import { edgeLevel, fillHoles } from "./_edges.js";
import { crop, morph } from "./_grid.js";

export const EDGE_SPREAD = 0.1;
export const REACH_PX = 10;

/** Every pixel of `region` 8-connected to a seed pixel (region & seed). */
function piecesTouching(region, seed, w, h) {
  const out = new Uint8Array(w * h);
  const stack = [];
  for (let i = 0; i < w * h; i++) if (region[i] && seed[i]) (out[i] = 1), stack.push(i);
  while (stack.length) {
    const i = stack.pop();
    const x = i % w, y = (i - x) / w;
    for (let dy = -1; dy <= 1; dy++) {
      for (let dx = -1; dx <= 1; dx++) {
        const xx = x + dx, yy = y + dy;
        if (xx < 0 || yy < 0 || xx >= w || yy >= h) continue;
        const j = yy * w + xx;
        if (region[j] && !out[j]) (out[j] = 1), stack.push(j);
      }
    }
  }
  return out;
}

/**
 * Length and width (px) with the edge drawn at `fraction - spread` (outer) and `+ spread` (inner), as
 * size_range() in Python. `mask` (0/1) and `diff` are grids of the same window; `feretFn(mask)` returns
 * [max Feret, min Feret] in px. Returns {length_px_outer, width_px_outer, length_px_inner, width_px_inner}.
 */
export function sizeRange(cv, mask, diff, feretFn, fraction = 0.5, spread = EDGE_SPREAD, reach = REACH_PX) {
  let x0 = Infinity, x1 = -1, y0 = Infinity, y1 = -1;
  for (let y = 0; y < mask.height; y++) {
    for (let x = 0; x < mask.width; x++) {
      if (!mask.data[y * mask.width + x]) continue;
      x0 = Math.min(x0, x), x1 = Math.max(x1, x), y0 = Math.min(y0, y), y1 = Math.max(y1, y);
    }
  }
  const pad = reach + 2;
  const [cx0, cy0] = [Math.max(0, x0 - pad), Math.max(0, y0 - pad)];
  const [cx1, cy1] = [Math.min(mask.width, x1 + pad + 1), Math.min(mask.height, y1 + pad + 1)];
  const m = crop(mask, cx0, cy0, cx1, cy1);
  const dc = crop(diff, cx0, cy0, cx1, cy1);
  const d = { ...dc, data: Float64Array.from(dc.data) };
  const contrast = edgeLevel(cv, m, d, 1.0);
  const near = morph(cv, "dilate", m, 2 * reach + 1, "ellipse");
  const out = {};
  for (const [name, f] of [["outer", fraction - spread], ["inner", fraction + spread]]) {
    const n = m.data.length;
    const level = f * contrast;
    const raw = new Uint8Array(n);
    for (let i = 0; i < n; i++) raw[i] = near.data[i] && d.data[i] >= level ? 1 : 0;
    const touching = piecesTouching(raw, m.data, m.width, m.height);
    let region = { width: m.width, height: m.height, channels: 1, data: touching };
    if (name === "outer") {
      for (let i = 0; i < n; i++) touching[i] |= m.data[i];
      region = fillHoles(cv, region);
    } else {
      for (let i = 0; i < n; i++) touching[i] &= m.data[i];
    }
    if (!region.data.some((v) => v)) region = m;
    [out[`length_px_${name}`], out[`width_px_${name}`]] = feretFn(region);
  }
  return out;
}
