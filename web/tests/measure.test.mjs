// Parity of the measurement port with Python's measure() (fixtures from dump_python_measure.py).
// The marching squares, skeleton, longest path, ImageJ perimeter and Feret tests are plain JS; the
// measure() tests are skipped when the pinned OpenCV.js hasn't been fetched: node web/scripts/fetch_opencv.mjs
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { gunzipSync } from "node:zlib";
import { fiberMetrics, longestPath, skeletonize, smoothLength } from "../src/measurement/fiber.js";
import { feret, findContours, measure, perimeterImageJ } from "../src/measurement/geometry.js";
import { loadOpenCVNode } from "./helpers.mjs";

const fixtures = new URL("fixtures/", import.meta.url);
const inputs = JSON.parse(gunzipSync(readFileSync(new URL("measure_inputs.json.gz", fixtures))));
const expected = JSON.parse(readFileSync(new URL("measure_expected.json", fixtures)));
const algorithms = JSON.parse(readFileSync(new URL("measure_algorithms.json", fixtures)));
const cv = await loadOpenCVNode();
const skip = cv ? false : "OpenCV.js not fetched (node web/scripts/fetch_opencv.mjs)";

function decode(b64, Type) {
  const buf = Buffer.from(b64, "base64");
  return new Type(buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.length));
}

const grid = (width, height, data, channels = 1) => ({ width, height, channels, data });

// Tolerance per field: [kind, value]; "abs" for an absolute difference, "rel" relative to the Python value.
const EXACT = ["abs", 1e-9];
const TOLERANCE = {
  perimeter_um: ["rel", 1e-6],
  circularity: ["rel", 1e-6],
  fiber_length_um: ["rel", 1e-9], // asked for: 1%
  fiber_width_um: ["rel", 1e-9],
  opacity: ["abs", 1e-6],
  _contrast: ["abs", 1e-6],
  length_um_outer: ["abs", 1e-6],
  width_um_outer: ["abs", 1e-6],
  length_um_inner: ["abs", 1e-6],
  width_um_inner: ["abs", 1e-6],
};
const COLOR = /^(?:[RGBSVHLab]_(?:mean|sd))$/;
const RELATIVE_EXACT = /_um2?$/;
const COLOR_CLASS_FIELDS = ["color_label", "color_confidence", "color_secondary", "color_secondary_fraction"];

function tolerance(key) {
  if (TOLERANCE[key]) return TOLERANCE[key];
  if (COLOR.test(key)) return ["abs", 0.5];
  return RELATIVE_EXACT.test(key) ? ["rel", 1e-9] : EXACT;
}

function runMeasure(c, options = {}) {
  const { width: w, height: h } = c;
  const labels = grid(w, h, Int32Array.from(decode(c.labels, Uint8Array)));
  const img = grid(w, h, decode(c.img, Uint8Array), 3);
  const diff = c.diff && grid(w, h, decode(c.diff, Float32Array));
  return measure(cv, labels, img, c.umPerPx, diff, 0.5, c.edgeMarginPx, {
    boxFn: (x, y) => `${String.fromCharCode(65 + Math.floor(y / c.cell))}${Math.floor(x / c.cell) + 1}`,
    lineMask: c.line && grid(w, h, decode(c.line, Uint8Array)),
    colorImg: c.color && grid(w, h, decode(c.color, Uint8Array), 3),
    bgImg: c.bg && grid(w, h, decode(c.bg, Float32Array), 3),
    ...options,
  });
}

const worst = {};

for (const c of inputs) {
  const ref = expected.find((e) => e.name === c.name);

  test(`measure matches Python: ${c.name}`, { skip }, () => {
    const rows = runMeasure(c);
    assert.equal(rows.length, ref.rows.length);
    rows.forEach((row, i) => {
      const want = ref.rows[i];
      const keys = Object.keys(want).filter((k) => !COLOR_CLASS_FIELDS.includes(k));
      assert.deepEqual(Object.keys(row).filter((k) => !COLOR_CLASS_FIELDS.includes(k)), keys);
      for (const k of COLOR_CLASS_FIELDS) assert.equal(row[k], undefined);
      for (const k of keys) {
        const [a, b] = [row[k], want[k]];
        const where = `${c.name} particle ${want.particle} ${k}`;
        if (k === "_px") {
          assert.deepEqual({ ...a, cx: 0, cy: 0 }, { ...b, cx: 0, cy: 0 }, where);
          assert.ok(Math.abs(a.cx - b.cx) < 1e-9 && Math.abs(a.cy - b.cy) < 1e-9, where);
        } else if (typeof b === "number") {
          const [kind, tol] = tolerance(k);
          const d = Math.abs(a - b) / (kind === "rel" ? Math.max(Math.abs(b), 1e-12) : 1);
          worst[k] = Math.max(worst[k] ?? 0, d);
          assert.ok(d <= tol, `${where}: JS ${a}, Python ${b} (${kind} difference ${d})`);
        } else if (b === null && typeof a === "number") {
          assert.ok(Number.isNaN(a), `${where}: JS ${a}, Python NaN/None`);
        } else {
          assert.equal(a, b, where);
        }
      }
    });
  });
}

test("measure passes the colour window and opacity to colorClasses", { skip }, () => {
  const c = inputs.find((x) => x.name === "two_colour_edge");
  const ref = expected.find((e) => e.name === c.name);
  const calls = [];
  const rows = runMeasure(c, {
    colorClasses: (img, mask, op) => {
      calls.push(op);
      assert.equal(img.type(), cv.CV_8UC3);
      assert.equal(mask.type(), cv.CV_8UC1);
      assert.deepEqual([mask.rows, mask.cols], [img.rows, img.cols]);
      const r = ref.rows[calls.length - 1];
      return { label: r.color_label, confidence: r.color_confidence, secondary: r.color_secondary,
        secondaryFraction: r.color_secondary_fraction };
    },
  });
  rows.forEach((row, i) => {
    assert.equal(calls[i], row.opacity);
    for (const k of COLOR_CLASS_FIELDS) assert.equal(row[k], ref.rows[i][k]);
  });
});

test("measure takes cv.Mat inputs", { skip }, () => {
  const c = inputs.find((x) => x.name === "two_colour_edge");
  const { width: w, height: h } = c;
  const mat = (type, data) => {
    const m = new cv.Mat(h, w, type);
    m[type === cv.CV_32S ? "data32S" : type % 8 === cv.CV_32F ? "data32F" : "data"].set(data);
    return m;
  };
  const labels = mat(cv.CV_32S, decode(c.labels, Uint8Array));
  const img = mat(cv.CV_8UC3, decode(c.img, Uint8Array));
  const diff = mat(cv.CV_32F, decode(c.diff, Float32Array));
  const bg = mat(cv.CV_32FC3, decode(c.bg, Float32Array));
  const rows = measure(cv, labels, img, c.umPerPx, diff, 0.5, c.edgeMarginPx, {
    boxFn: (x, y) => `${String.fromCharCode(65 + Math.floor(y / c.cell))}${Math.floor(x / c.cell) + 1}`,
    bgImg: bg,
  });
  [labels, img, diff, bg].forEach((m) => m.delete());
  assert.deepEqual(rows, runMeasure(c));
});

test("worst differences from Python, per field", { skip }, (t) => {
  for (const [k, v] of Object.entries(worst).sort()) t.diagnostic(`${k}: ${tolerance(k)[0]} ${v.toExponential(2)}`);
});

test("marching squares matches skimage find_contours", () => {
  for (const c of algorithms.contours) {
    const got = findContours(decode(c.field, Float64Array), c.width, c.height, c.level);
    assert.deepEqual(got, c.contours);
  }
});

test("skeleton, longest path and fiber metrics match skimage, SciPy and Python", () => {
  for (const c of algorithms.skeletons) {
    const mask = grid(c.width, c.height, decode(c.mask, Uint8Array));
    const skel = skeletonize(mask);
    assert.deepEqual(Array.from(skel), Array.from(decode(c.skeleton, Uint8Array)));
    const path = longestPath(skel, c.width, c.height);
    assert.deepEqual(path, c.path);
    assert.ok(Math.abs(smoothLength(path) - c.smoothLength) < 1e-9);
    const [length, width, uniform] = fiberMetrics(mask);
    assert.ok(Math.abs(length - c.fiber[0]) < 1e-9 && Math.abs(width - c.fiber[1]) < 1e-9, `${length} vs ${c.fiber[0]}`);
    assert.equal(uniform, c.fiber[2]);
  }
});

test("ImageJ traced perimeter matches Python", () => {
  for (const c of algorithms.perimeters) {
    const got = perimeterImageJ(grid(c.width, c.height, decode(c.mask, Uint8Array)));
    assert.ok(Math.abs(got - c.perimeter) < 1e-9, `${got} vs ${c.perimeter}`);
  }
});

test("Feret over a hull matches Python", () => {
  for (const c of algorithms.ferets) {
    feret(c.hull).forEach((v, i) => assert.ok(Math.abs(v - c.feret[i]) < 1e-9, `${v} vs ${c.feret[i]}`));
  }
});
