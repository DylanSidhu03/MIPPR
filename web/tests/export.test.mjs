// Parity of the colour rules, morphology rules and export (CSV rows, summary and text) with pipeline/mippr
// (fixtures from dump_python_export.py). Rows must be identical: same keys, same values, floats exactly equal.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { COLOR_CLASSES, COLOR_RULES_VERSION, PIXEL_CLASSES, SHADES, colorClasses, labelFromLab, pixelClasses }
  from "../src/color/rules.js";
import { MORPHOLOGY_CLASSES, morphologyRules } from "../src/morphology/rules.js";
import { COLUMNS, FLAGS, NOTE, SUMMARY_COLUMNS, buildRows, buildSummary, noteTxt, particlesCsv, pyFloat, summaryCsv,
  toCsv } from "../src/export/csv.js";
import { loadOpenCVNode } from "./helpers.mjs";

const NONFINITE = { nan: NaN, inf: Infinity, "-inf": -Infinity };
const load = (name) => JSON.parse(readFileSync(new URL(`fixtures/${name}`, import.meta.url)),
  (_, v) => (v && typeof v === "object" && !Array.isArray(v) && Object.keys(v).length === 1 && "float" in v
    ? NONFINITE[v.float] : v));
const rules = load("export_rules.json");
const ref = load("export_rows.json");
const flat = (lab) => lab.flat();
const asTuple = (r) => [r.label, r.confidence, r.secondary, r.secondaryFraction];

test("colour constants match Python", () => {
  const c = rules.color;
  assert.equal(COLOR_RULES_VERSION, c.version);
  assert.deepEqual([...COLOR_CLASSES], c.classes);
  assert.deepEqual([...PIXEL_CLASSES], c.pixelClasses);
  assert.deepEqual(SHADES.map((p) => [...p].sort()).sort(), c.shades);
});

test("pixel classes match Python", () => {
  const { lab, classes } = rules.color.pixels;
  assert.deepEqual(pixelClasses(flat(lab)), classes);
});

test("particle colour labels match Python (multicolour, shade pairs, clear)", () => {
  for (const [i, c] of rules.color.labels.entries()) {
    assert.deepEqual(asTuple(labelFromLab(flat(c.lab), c.opacity)), c.result, `case ${i}`);
  }
});

const cv = await loadOpenCVNode();

test("colorClasses on images matches Python", { skip: !cv && "web/vendor/ not fetched" }, () => {
  for (const [i, c] of rules.color.images.entries()) {
    const [h, w] = c.shape;
    const img = cv.matFromArray(h, w, cv.CV_8UC3, c.bgr);
    const rgba = new cv.Mat();
    cv.cvtColor(img, rgba, cv.COLOR_BGR2RGBA);
    try {
      assert.deepEqual(asTuple(colorClasses(cv, img, c.mask, c.opacity)), c.result, `image ${i} (BGR)`);
      assert.deepEqual(asTuple(colorClasses(cv, rgba, c.mask, c.opacity)), c.result, `image ${i} (RGBA)`);
    } finally {
      img.delete();
      rgba.delete();
    }
  }
});

test("morphology rules match Python", () => {
  assert.deepEqual([...MORPHOLOGY_CLASSES], rules.morphology.classes);
  for (const { args, result } of rules.morphology.cases) {
    const r = morphologyRules(...args);
    assert.deepEqual([r.label, r.confidence, r.runnerUp, r.runnerUpConfidence], result, JSON.stringify(args));
  }
});

test("export constants match Python", () => {
  assert.deepEqual([...COLUMNS], ref.columns);
  assert.deepEqual([...SUMMARY_COLUMNS], ref.summaryColumns);
  assert.deepEqual([...FLAGS], ref.flags);
  assert.equal(NOTE, ref.note);
  assert.equal(noteTxt(), `${ref.note}\n`);
});

test("floats are written as Python's repr()", () => {
  for (const [x, s] of ref.floats) assert.equal(pyFloat(x), s, String(x));
  assert.equal(toCsv([{ a: "" }, { a: 'say "hi"' }, { a: "x\ry" }, { a: null }], ["a"]), ref.csvOddCells);
});

function rowsFor(run) {
  const a = run.args;
  return buildRows(run.measurements, { sampleId: a.sample_id, pictureLabel: a.picture_label, imageId: a.image_id,
    metadata: a.metadata, appVersion: a.app_version, mmPerPx: a.mm_per_px, processedAt: a.processed_at,
    backgroundType: a.background_type, scaleSource: a.scale_source, scaleFlag: a.scale_flag });
}

for (const run of ref.runs) {
  test(`rows and particles.csv match Python: ${run.args.picture_label}`, () => {
    const rows = rowsFor(run);
    assert.deepEqual(rows, run.rows);
    rows.forEach((r) => assert.deepEqual(Object.keys(r), [...COLUMNS]));
    assert.equal(particlesCsv(rows), run.csv);
  });
}

test("summary and summary.csv match Python", () => {
  const rows = ref.runs.flatMap(rowsFor);
  for (const [i, status] of Object.entries(ref.review)) rows[i].review_status = status;
  rows[2].morphology_label = "film";
  const summary = buildSummary(rows);
  assert.deepEqual(summary, ref.summary);
  summary.forEach((s) => assert.deepEqual(Object.keys(s), [...SUMMARY_COLUMNS]));
  assert.equal(summaryCsv(rows), ref.summaryCsv);
});
