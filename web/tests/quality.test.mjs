// Parity of the photo quality check and the white balance with Python (fixture from dump_python_quality.py).
// The fixture keeps only the good photos; each case's degradation steps are applied here as Python did.
// Skips when the pinned OpenCV.js hasn't been fetched: node web/scripts/fetch_opencv.mjs
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { checkQuality, measureQuality, Problem } from "../src/capture/quality.js";
import { findSheet, whiteBalance } from "../src/capture/sheet.js";
import { loadOpenCVNode } from "./helpers.mjs";
import { readPngMat } from "./png_color.mjs";

const fixtures = new URL("fixtures/", import.meta.url);
const ref = JSON.parse(readFileSync(new URL("quality.json", fixtures)));
const cv = await loadOpenCVNode();
const skip = cv ? false : "OpenCV.js not fetched (node web/scripts/fetch_opencv.mjs)";

// Largest JS - Python difference accepted per metric (the metrics are rounded as in Python).
const TOLERANCE = {
  px_per_mm: 0.01, edge_width_px: 0.05, edge_width_mm: 0.005, white_level: 0.5, clipped_share: 0.002,
  white_clipped: 0.005, glare_mm2: 0.05, light_ratio: 0.005, grey_spread: 0.5,
};

/** Per-pixel float maths of the numpy degradations, then truncation to uint8 like astype(np.uint8). */
function perPixel(p, fn) {
  const d = p.data, w = p.cols, cn = p.channels();
  for (let i = 0; i < d.length; i++) {
    const px = Math.floor(i / cn);
    const v = fn(d[i], px % w, Math.floor(px / w), i % cn);
    d[i] = Math.trunc(Math.min(255, Math.max(0, v)));
  }
  return p;
}

function degrade(p, [kind, arg]) {
  const out = new cv.Mat();
  const f32 = Math.fround;
  switch (kind) {
    case "gauss":
      cv.GaussianBlur(p, out, new cv.Size(0, 0), arg, 0, cv.BORDER_DEFAULT);
      break;
    case "motion": {
      const k = cv.Mat.zeros(arg, arg, cv.CV_32F);
      for (let j = 0; j < arg; j++) k.floatPtr(arg >> 1, j)[0] = 1 / arg;
      cv.filter2D(p, out, -1, k, new cv.Point(-1, -1), 0, cv.BORDER_DEFAULT);
      k.delete();
      break;
    }
    case "resize":
      cv.resize(p, out, new cv.Size(0, 0), arg, arg, cv.INTER_AREA);
      break;
    case "scale":
      p.copyTo(out);
      perPixel(out, (v) => v * arg);
      break;
    case "glare": {
      p.copyTo(out);
      const [w, h] = [p.cols, p.rows];
      perPixel(out, (v, x, y) => v + 255 * Math.min(1, Math.max(0, 1.5 - Math.hypot(x - w / 2, y - h / 2) / arg)));
      break;
    }
    case "shadow": {
      p.copyTo(out);
      const w = p.cols;
      perPixel(out, (v, x) => v * (1 - (1 - arg) * Math.min(1, Math.max(0, (x - 0.45 * w) / (0.1 * w)))));
      break;
    }
    case "tint":
      p.copyTo(out);
      perPixel(out, (v, x, y, k) => {
        const q = f32(v / 255);
        return f32((k === 0 ? f32(q ** 0.7) : q) * 255);
      });
      break;
    case "cover":
      p.copyTo(out);
      for (const [x0, y0, x1, y1] of arg) {
        for (let y = Math.max(0, y0); y < Math.min(out.rows, y1); y++) {
          for (let x = Math.max(0, x0); x < Math.min(out.cols, x1); x++) out.data.set([60, 50, 40], 3 * (y * out.cols + x));
        }
      }
      break;
    default:
      throw new Error(kind);
  }
  p.delete();
  return out;
}

const bases = {};
function photo(c) {
  bases[c.photo] ??= readPngMat(cv, new URL(c.photo, fixtures).pathname);
  return c.steps.reduce(degrade, bases[c.photo].clone());
}

function close(a, b, tol, what) {
  if (Array.isArray(b)) return b.forEach((v, i) => close(a[i], v, tol, `${what}[${i}]`));
  if (b === null || tol === undefined) return assert.deepEqual(a, b, what);
  assert.ok(Math.abs(a - b) <= tol, `${what}: JS ${a}, Python ${b}`);
}

for (const c of ref.cases) {
  test(`quality check matches Python: ${c.background} ${c.name}${c.useSheet ? "" : " (no sheet)"}`, { skip }, (t) => {
    const p = photo(c);
    let sheet = null;
    if (c.useSheet) {
      try {
        sheet = findSheet(cv, p);
      } catch {
        sheet = null;
      }
    }
    assert.equal(sheet !== null, c.sheetFound, "sheet found");
    if (sheet) assert.equal(sheet.pxPerMm, c.pxPerMm);
    const m = measureQuality(cv, p, sheet);
    assert.deepEqual(Object.keys(m).sort(), Object.keys(c.metrics).sort());
    for (const [k, v] of Object.entries(c.metrics)) close(m[k], v, TOLERANCE[k], k);
    const probs = checkQuality(cv, p, sheet, { metrics: m });
    assert.deepEqual(probs.map((q) => q.code), c.problems.map((q) => q.code));
    probs.forEach((q, i) => {
      const want = c.problems[i];
      assert.ok(q instanceof Problem);
      assert.equal(q.message, want.message);
      close(q.limit, want.limit, 0, `${q.code} limit`);
      close(q.value, want.value, TOLERANCE[{ low_resolution: "px_per_mm", blurry: m.edge_width_mm != null ? "edge_width_mm" : "edge_width_px", too_dark: "white_level", overexposed: "clipped_share", glare: "glare_mm2", uneven_light: "light_ratio", color_cast: "grey_spread" }[q.code]] ?? 0, `${q.code} value`);
    });
    if (sheet) {
      const { gains, report } = whiteBalance(cv, sheet, p);
      close(gains, c.whiteBalance.gains, 1e-3, "gains");
      for (const [k, v] of Object.entries(c.whiteBalance.report)) close(report[k], v, k.startsWith("gains") ? 1e-3 : 0.1, k);
    }
    t.diagnostic(JSON.stringify(m));
    p.delete();
  });
}
