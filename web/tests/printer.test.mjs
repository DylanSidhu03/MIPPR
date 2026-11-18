// Parity of the printer-scale check (src/capture/printer.js) with calibration.py printer_scale
// (fixtures from dump_python_printer.py). Skipped when the pinned OpenCV.js hasn't been fetched.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { lensModel, printerProblem, printerScale } from "../src/capture/printer.js";
import { findSheet } from "../src/capture/sheet.js";
import { loadOpenCVNode } from "./helpers.mjs";
import { readPngMat } from "./png_color.mjs";

const fixtures = new URL("fixtures/", import.meta.url);
const ref = JSON.parse(readFileSync(new URL("printer.json", fixtures)));
const cv = await loadOpenCVNode();
const skip = cv ? false : "OpenCV.js not fetched (node web/scripts/fetch_opencv.mjs)";

for (const c of ref.cases) {
  test(`printer scale matches Python: ${c.photo}`, { skip }, () => {
    const img = readPngMat(cv, new URL(c.photo, fixtures).pathname);
    try {
      const sheet = findSheet(cv, img);
      const lens = lensModel(cv, sheet, img);
      assert.ok(Math.abs(lens.q - c.q) < 2e-3, `q: JS ${lens.q}, Python ${c.q}`);
      const ps = printerScale(cv, sheet, img);
      const want = c.printerScale;
      assert.equal(ps.paper, want.paper);
      // The flattened photo differs from Python's by up to a grey level (OpenCV.js 4.10 vs 5), so the
      // edges agree to a few hundredths of a mm and the scale to a few parts in 10,000.
      for (const k of ["scale", "scale_x", "scale_y"]) {
        assert.equal(ps[k] === null, want[k] === null, k);
        if (want[k] !== null) assert.ok(Math.abs(ps[k] - want[k]) <= 5e-4, `${k}: JS ${ps[k]}, Python ${want[k]}`);
      }
      for (const [side, v] of Object.entries(want.edges_mm)) {
        assert.equal(ps.edges_mm[side] === null, v === null, side);
        if (v !== null) assert.ok(Math.abs(ps.edges_mm[side] - v) <= 0.1, `${side}: JS ${ps.edges_mm[side]}, Python ${v}`);
      }
      const p = printerProblem(ps), pl = printerProblem(ps, 98.5);
      assert.equal(p?.code ?? null, c.problem?.code ?? null);
      assert.equal(pl?.code ?? null, c.problemWithLine?.code ?? null);
      if (p) assert.equal(p.message, c.problem.message);
    } finally {
      img.delete();
    }
  });
}
