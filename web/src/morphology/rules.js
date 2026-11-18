// Part 5: browser port of pipeline/mippr/morphology/rules.py (the v2 rules; the v3 image model is model.js).
// Fiber (length:width >= 3, or too thin to measure a width), pellet (round, solid, about as wide as long) and film
// (mostly see-through). Everything else is fragment with confidence 0.5: "the rules can't tell".
// Parity with the Python reference is checked by web/tests/export.test.mjs.

export const MORPHOLOGY_CLASSES = Object.freeze(["fragment", "rubbery_fragment", "fiber", "film", "foam", "pellet",
  "other"]);
export const FIBER_ASPECT = 3.0; // decided: length:width >= 3:1
export const PELLET_CIRCULARITY = 0.85;
export const PELLET_SOLIDITY = 0.95;
export const PELLET_ASPECT = 1.3;
export const FILM_OPACITY = 0.5;

// Python's math.exp is glibc's exp, a table-driven algorithm that isn't correctly rounded and so differs from
// Math.exp in the last bit now and then; the confidences are written to the CSV in full, so it is ported here.
// This is the FMA build (x86-64 with FMA, as on the machine the fixtures come from); glibc built without FMA can
// differ from it in the last bit too (about 1 in 1000 values).
const EXP_N = 128;
const [INV_LN2_N, SHIFT, NEG_LN2_HI_N, NEG_LN2_LO_N, C2, C3, C4, C5] = ["0x1.71547652b82fep7", "0x1.8p52",
  "-0x1.62e42fefa0000p-8", "-0x1.cf79abc9e3b3ap-47", "0x1.ffffffffffdbdp-2", "0x1.555555555543cp-3",
  "0x1.55555cf172b91p-5", "0x1.1111167a4d017p-7"].map(hexFloat);

const view = new DataView(new ArrayBuffer(8));
const bitsOf = (x) => (view.setFloat64(0, x), view.getBigUint64(0));
const fromBits = (b) => (view.setBigUint64(0, BigInt.asUintN(64, b)), view.getFloat64(0));

function hexFloat(s) {
  const [, sign, int, frac, exp] = /^(-?)0x(\d)\.?([0-9a-f]*)p([-+]?\d+)$/.exec(s);
  const v = (Number(int) + (frac ? parseInt(frac, 16) / 16 ** frac.length : 0)) * 2 ** Number(exp);
  return sign ? -v : v;
}

/** A finite double as [m, e] with value m * 2 ** e (m a BigInt). */
function split(x) {
  const b = bitsOf(x);
  const be = Number((b >> 52n) & 0x7ffn);
  let m = b & 0xfffffffffffffn;
  if (be) m |= 1n << 52n;
  return [b >> 63n ? -m : m, (be || 1) - 1075];
}

/** a * b + c with one rounding (the hardware FMA), from the exact value. */
function fma(a, b, c) {
  const [ma, ea] = split(a);
  const [mb, eb] = split(b);
  const [mc, ec] = split(c);
  const e = Math.min(ea + eb, ec);
  const m = ((ma * mb) << BigInt(ea + eb - e)) + (mc << BigInt(ec - e));
  if (!m) return a * b + c;
  return roundBig(m, BigInt(-e));
}

/** The double nearest to n / d / 2 ** p (BigInts, d > 0), rounded once. */
function roundBig(n, p, d = 1n) {
  const neg = n < 0n;
  let q = (neg ? -n : n) / d;
  const exact = q * d === (neg ? -n : n);
  const shift = BigInt(Math.max(0, q.toString(2).length - 64));
  const sticky = exact && !(q & ((1n << shift) - 1n)) ? 0n : 1n;
  q = (q >> shift) | sticky;
  const v = Number(q) * 2 ** Number(shift - p);
  return neg ? -v : v;
}

const EXP_TABLE = (() => {
  // 2 ** (k / N) ~= H * (1 + T): stored as the bits of T, and the bits of H minus k << 45 (glibc's __exp_data.tab).
  const P = 160n;
  const tab = [];
  for (let k = 0; k < EXP_N; k++) {
    const a = 1n << (BigInt(k) + P * BigInt(EXP_N));
    let y = BigInt(Math.round(2 ** (k / EXP_N) * 2 ** 52)) << (P - 52n);
    for (let i = 0; i < 3; i++) y = (127n * y + a / y ** 127n) / 128n; // y = 2 ** (k / N) * 2 ** P
    const h = roundBig(y, P);
    const hb = BigInt(h * 2 ** 52) << (P - 52n);
    const t = roundBig((y - hb) << 200n, 200n, hb);
    tab.push(bitsOf(t), bitsOf(h) - (BigInt(k) << 45n));
  }
  return tab;
})();

/** glibc's exp for |x| < 512 (enough here: the rules clamp it to |x| <= 200). */
function exp(x) {
  if (Math.abs(x) < 2 ** -54) return 1 + x;
  if (!(Math.abs(x) < 512)) return Math.exp(x);
  let kd = INV_LN2_N * x + SHIFT;
  const ki = bitsOf(kd);
  kd -= SHIFT;
  const r = fma(kd, NEG_LN2_LO_N, fma(kd, NEG_LN2_HI_N, x));
  const idx = 2 * Number(ki % BigInt(EXP_N));
  const tail = fromBits(EXP_TABLE[idx]);
  const scale = fromBits(EXP_TABLE[idx + 1] + (ki << 45n));
  const r2 = r * r;
  const tmp = fma(r2 * r2, fma(r, C5, C4), fma(r2, fma(r, C3, C2), tail + r));
  return fma(scale, tmp, scale);
}

/** Confidence that a value is on the class's side of a threshold: 0.5 at the threshold. */
function conf(value, threshold, higherIsMore, scale) {
  if (value === null || value === undefined || Number.isNaN(value)) return 0.0;
  const z = higherIsMore ? (value - threshold) / scale : (threshold - value) / scale;
  return 1 / (1 + exp(-4 * Math.max(-50.0, Math.min(50.0, z)))); // clamped: extreme shapes mustn't overflow
}

/** {label, confidence, runnerUp, runnerUpConfidence} from the v2 rules; `opacity` is null when unknown. */
export function morphologyRules(aspect, circularity, solidity, opacity = null, widthUnresolved = false) {
  const scores = new Map();
  scores.set("fiber", widthUnresolved ? 0.99 : conf(aspect, FIBER_ASPECT, true, 1.0));
  scores.set("pellet", Math.min(conf(circularity, PELLET_CIRCULARITY, true, 0.05),
    conf(solidity, PELLET_SOLIDITY, true, 0.03), conf(aspect, PELLET_ASPECT, false, 0.15)));
  if (opacity !== null && opacity !== undefined) {
    scores.set("film", Math.min(conf(opacity, FILM_OPACITY, false, 0.15), 1 - scores.get("fiber")));
  }
  const ranked = [...scores].sort((a, b) => b[1] - a[1]); // stable: ties keep fiber, pellet, film order
  const [best, top] = ranked[0];
  if (top >= 0.5) {
    let runner = ranked.length > 1 ? ranked[1] : ["fragment", 0.5];
    if (runner[1] < 0.5) runner = ["fragment", 1 - top];
    return { label: best, confidence: top, runnerUp: runner[0], runnerUpConfidence: runner[1] };
  }
  return { label: "fragment", confidence: 0.5, runnerUp: best, runnerUpConfidence: top };
}
