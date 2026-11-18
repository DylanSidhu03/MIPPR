// End to end: a sheet photo through the whole browser pipeline (runGrid) against Python's run_grid.
// Fixture from dump_python_pipeline.py. Skips when OpenCV.js hasn't been fetched.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { APP_VERSION, imageIdFor, runGrid } from "../src/pipeline.js";
import { COLUMNS } from "../src/export/csv.js";
import { loadOpenCVNode } from "./helpers.mjs";
import { readPngMat } from "./png_color.mjs";

const fixtures = new URL("fixtures/", import.meta.url);
const ref = JSON.parse(readFileSync(new URL("pipeline.json", fixtures)));
const cv = await loadOpenCVNode();
const skip = cv ? false : "OpenCV.js not fetched (node web/scripts/fetch_opencv.mjs)";

const value = (v) => (v && typeof v === "object" && "float" in v ? Number(v.float.replace("nan", "NaN")) : v);

test("the app version matches the Python package", () => {
  const init = readFileSync(new URL("../../pipeline/mippr/__init__.py", import.meta.url), "utf8");
  assert.equal(APP_VERSION, init.match(/__version__\s*=\s*"([^"]+)"/)[1]);
});

for (const c of ref) {
  test(`runGrid matches run_grid: ${c.file}`, { skip }, async () => {
    const bytes = readFileSync(new URL(c.file, fixtures));
    const imageId = await imageIdFor(c.file, bytes);
    assert.equal(imageId, c.rows[0].image_id);
    const img = readPngMat(cv, new URL(c.file, fixtures));
    const { rows, run, crops } = runGrid(cv, img, {
      sampleId: c.sample_id, photo: c.photo, imageId, photoFile: c.file, metadata: c.metadata, lineMm: c.line_mm,
      processedAt: c.rows[0].processed_at, forDisplay: true,
    });
    // Crops (crops.js vs crops.py): same files; sizes within 2 px and opaque areas within 15%, as the
    // outlines can differ by an edge pixel.
    assert.deepEqual(crops.map((k) => k.file), c.crops.map((k) => k.file));
    crops.forEach((k, i) => {
      const want = c.crops[i];
      assert.ok(Math.abs(k.width - want.width) <= 2 && Math.abs(k.height - want.height) <= 2, `${k.file} size`);
      let opaque = 0;
      for (let j = 3; j < k.rgba.length; j += 4) opaque += k.rgba[j] === 255;
      assert.ok(Math.abs(opaque - want.opaque) <= 0.15 * want.opaque + 4, `${k.file} opaque ${opaque} vs ${want.opaque}`);
    });
    img.delete();
    assert.equal(run.background_type, c.run.background_type);
    assert.equal(run.markers_found, c.run.markers_found);
    assert.ok(Math.abs(run.px_per_mm - c.run.px_per_mm) < 1e-9);
    // The printer scale comes from edges found to a few hundredths of a mm, so its value (and the scale it
    // corrects) agrees to a few parts in 10,000; everything else in the quality report is identical.
    const strip = (ps) => ps.map((q) => (q.code === "printer_scaled" ? { ...q, value: null } : q));
    assert.deepEqual(strip(run.quality.problems), strip(c.run.quality.problems));
    run.quality.problems.forEach((q, i) => q.code === "printer_scaled" &&
      assert.ok(Math.abs(q.value - c.run.quality.problems[i].value) <= 5e-4, "printer scale"));
    assert.equal(run.printed_line_mm, c.run.printed_line_mm);
    assert.equal(run.printer_scale.paper, c.run.printer_scale.paper);
    assert.ok(Math.abs(run.mm_per_px - c.run.mm_per_px) <= 5e-4 * c.run.mm_per_px, "mm_per_px");
    assert.deepEqual(rows.map((r) => r.particle_ref), c.rows.map((r) => r.particle_ref));
    // The flattened grid differs from Python's by at most 1 grey level on a few pixels (OpenCV.js 4.10 vs
    // OpenCV 5's remap), which can flip an edge pixel at the threshold. So text and flags must be identical,
    // and numbers agree within a pixel or so: colour within 1.5 Lab units (6 levels for the hex code and the
    // RGB/HSV means, 6 degrees for hue), other
    // values within 7% (a 0.6 mm particle is only about 60 px in area; larger ones agree within 0.3%).
    // Rule confidences come from a steep curve over the shape values, so they get 0.1 (absolute).
    const worst = {};
    rows.forEach((r, i) => {
      for (const k of COLUMNS) {
        const want = value(c.rows[i][k]);
        const got = r[k] ?? "";
        const where = `${r.particle_id} ${k}: JS ${got}, Python ${want}`;
        if (k === "color_hex") {
          const ch = (h) => [1, 3, 5].map((j) => parseInt(h.slice(j, j + 2), 16));
          ch(got).forEach((v, j) => assert.ok(Math.abs(v - ch(want)[j]) <= 6, where));
        } else if (typeof want === "number" && typeof got === "number") {
          if (Number.isNaN(want)) {
            assert.ok(Number.isNaN(got), where);
            continue;
          }
          const d = Math.abs(got - want);
          const absolute = k.startsWith("color_") || k.endsWith("confidence");
          worst[k] = Math.max(worst[k] ?? 0, absolute ? d : d / Math.max(1e-9, Math.abs(want)));
          const limit = k.endsWith("confidence") ? 0.1 : /^color_[RGBHSV]$/.test(k) ? 6
            : k.startsWith("color_") ? 1.5 : 0.07 * Math.abs(want) + 1e-9;
          assert.ok(d <= limit, where);
        } else assert.equal(got, want ?? "", where);
      }
    });
    const off = Object.entries(worst).filter(([, d]) => d > 1e-6).map(([k, d]) => `${k} ${d.toPrecision(2)}`);
    console.log(`${c.file}: ${rows.length} rows identical in text and flags; numbers differing: ${off.join(", ") || "none"}`);
  });
}
