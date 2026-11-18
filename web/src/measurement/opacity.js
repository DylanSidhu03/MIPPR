// Part 3: browser port of pipeline/mippr/measurement/opacity.py.
// How much of the known background a particle blocks: 0 (see-through) to 1 (opaque).
import { count, morph } from "../grids.js";

function median(vals) {
  const s = Float64Array.from(vals).sort();
  const n = s.length;
  return n % 2 ? s[(n - 1) / 2] : (s[n / 2 - 1] + s[n / 2]) / 2;
}

const mean = (vals) => vals.reduce((a, b) => a + b, 0) / vals.length;
const clip01 = (v) => Math.min(1, Math.max(0, v));

/**
 * Opacity of one particle from the image `img` and the background expected behind it `bg` (3-channel
 * grids of the same window as the 0/1 `mask`, any depth), as opacity() in Python. A lower bound from the
 * largest possible colour change on one background; measured directly where the particle lies across
 * a light and a dark box. Null when fewer than `minPx` interior pixels remain.
 */
export function opacity(cv, img, bg, mask, minPx = 4) {
  const m = morph(cv, "erode", mask, 3);
  if (count(m) < minPx) return null;
  const o = [], b = [];
  for (let i = 0; i < m.data.length; i++) {
    if (!m.data[i]) continue;
    o.push([img.data[3 * i], img.data[3 * i + 1], img.data[3 * i + 2]]);
    b.push([bg.data[3 * i], bg.data[3 * i + 1], bg.data[3 * i + 2]]);
  }
  const grey = (p) => (p[0] + p[1] + p[2]) / 3;
  const gb = b.map(grey);
  const dark = gb.map((v) => v < 128);
  const k = dark.filter(Boolean).length, n = dark.length;
  if (k / n > 0.2 && (n - k) / n > 0.2) {
    const lightBg = mean(gb.filter((_, i) => !dark[i])), darkBg = mean(gb.filter((_, i) => dark[i]));
    if (lightBg - darkBg > 60) {
      const seen = Math.abs(median(o.filter((_, i) => !dark[i]).map(grey)) - median(o.filter((_, i) => dark[i]).map(grey)));
      return clip01(1 - seen / (lightBg - darkBg));
    }
  }
  const frac = o.map((p, i) => {
    let mx = -Infinity;
    for (let c = 0; c < 3; c++) {
      const room = p[c] < b[i][c] ? b[i][c] : 255 - b[i][c];
      mx = Math.max(mx, Math.abs(p[c] - b[i][c]) / Math.max(room, 1));
    }
    return mx;
  });
  return clip01(median(frac));
}
