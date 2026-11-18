// Part 6: the review rules (review/corrections.js) against Python's review/corrections.py.
// Fixture from dump_python_review.py. The edit_outline cases need OpenCV.js and skip when it hasn't been fetched.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { COLUMNS } from "../src/export/csv.js";
import { imageIdFor, runGrid } from "../src/pipeline.js";
import { GRID_SEGMENT_DEFAULTS, segmentGrid } from "../src/segmentation/grid.js";
import { REMEASURED, apply, applyAll, decisionFromPython, kept, parseTime, reviewQueue } from "../src/review/corrections.js";
import { photoContext } from "../src/review/context.js";
import { loadOpenCVNode } from "./helpers.mjs";
import { readPngMat } from "./png_color.mjs";

const fixtures = new URL("fixtures/", import.meta.url);
const ref = JSON.parse(readFileSync(new URL("review.json", fixtures)));
const cv = await loadOpenCVNode();
const skip = cv ? false : "OpenCV.js not fetched (node web/scripts/fetch_opencv.mjs)";

const value = (v) => (v && typeof v === "object" && "float" in v ? Number(v.float.replace("nan", "NaN")) : v);
const fromJson = (r) => (r === null ? r : Object.fromEntries(Object.entries(r).map(([k, v]) => [k, value(v)])));
const rows = ref.rows.map(fromJson);

/** Each step's row (or error) from applying the sequence's decisions one at a time. */
function runSequence(seq, context, check) {
  let row = rows.find((r) => r.particle_ref === seq.ref);
  seq.decisions.forEach((d, i) => {
    const want = seq.steps[i];
    const where = `${seq.ref} step ${i} (${d.action})`;
    if (want.error) {
      const name = want.type === "NotImplementedError" ? want.type : "Error";
      assert.throws(() => apply(row, decisionFromPython(d), context), { message: want.error, name }, where);
      return;
    }
    const before = { ...row };
    const out = apply(row, decisionFromPython(d), context);
    assert.deepEqual(row, before, `${where}: the input row changed`);
    check(out, fromJson(want.row), where);
    row = out;
  });
}

function same(got, want, where) {
  assert.deepEqual(Object.keys(got), Object.keys(want), where);
  assert.deepEqual(got, want, where);
}

test("pipeline rows have the particles.csv columns", () => {
  for (const r of rows) assert.deepEqual(Object.keys(r), [...COLUMNS]);
});

test("apply matches Python on every decision sequence and validation error", () => {
  for (const seq of ref.sequences) runSequence(seq, seq.context ? {} : null, same);
});

test("applyAll matches Python (time order, ties, unknown and duplicate particles, bad times)", () => {
  for (const c of ref.apply_all) {
    const input = c.rows ? c.rows.map(fromJson) : rows;
    const decisions = c.decisions.map(decisionFromPython);
    if (c.error) {
      assert.throws(() => applyAll(input, decisions), { message: c.error });
      continue;
    }
    const out = applyAll(input, decisions);
    assert.equal(out.length, c.out.length);
    out.forEach((r, i) => same(r, fromJson(c.out[i]), `applyAll row ${i}`));
    assert.deepEqual(kept(out).map((r) => r.particle_ref),
      c.out.filter((r) => r.review_status !== "rejected").map((r) => r.particle_ref));
  }
});

test("parseTime reads ISO 8601 as Python's fromisoformat does", () => {
  for (const t of ref.times) {
    if (t.error) assert.throws(() => parseTime(t.at), { message: t.error }, t.at);
    else assert.equal(parseTime(t.at), BigInt(t.micros), t.at);
  }
});

test("reviewQueue orders rows as Python's review_queue", () => {
  for (const q of ref.queues) {
    const input = q.rows.map(fromJson);
    const out = reviewQueue(input);
    assert.deepEqual(out.map((r) => r.particle_ref), q.order);
    assert.ok(out.every((r) => input.includes(r)), "rows are not copied");
  }
});

// Re-measured values differ from Python's within the end-to-end tolerances of pipeline.test.mjs (the flattened
// grid differs by up to a grey level between OpenCV.js 4.10 and OpenCV 5); text and flags are identical.
function close(got, want, where) {
  assert.deepEqual(Object.keys(got), Object.keys(want), where);
  for (const k of Object.keys(want)) {
    const [g, w] = [got[k], want[k]];
    const at = `${where} ${k}: JS ${g}, Python ${w}`;
    if (k === "color_hex") {
      const ch = (h) => [1, 3, 5].map((j) => parseInt(h.slice(j, j + 2), 16));
      ch(g).forEach((v, j) => assert.ok(Math.abs(v - ch(w)[j]) <= 6, at));
    } else if (typeof w === "number" && typeof g === "number") {
      if (Number.isNaN(w)) assert.ok(Number.isNaN(g), at);
      else {
        const limit = k.endsWith("confidence") ? 0.1 : k.startsWith("color_") ? 1.5 : 0.07 * Math.abs(w) + 1e-9;
        assert.ok(Math.abs(g - w) <= limit, at);
      }
    } else assert.equal(g, w, at);
  }
}

test("split and merge match Python (new ids, rejected originals, derived_from, re-measured pieces)", { skip }, () => {
  const context = photoContext(cv, readPngMat(cv, new URL(ref.file, fixtures).pathname));
  try {
    for (const c of ref.lists) {
      const decisions = c.decisions.map(decisionFromPython);
      const contexts = { [rows[0].image_id]: context };
      if (c.error) {
        assert.throws(() => applyAll(rows, decisions, contexts), { message: c.error });
        continue;
      }
      const out = applyAll(rows, decisions, contexts);
      assert.deepEqual(out.map((r) => r.particle_ref), c.out.map((r) => r.particle_ref));
      out.forEach((r, i) => close(r, fromJson(c.out[i]), `${c.decisions.map((x) => x.action).join("+")} row ${i}`));
    }
  } finally {
    context.delete();
  }
});

test("edit_outline re-measures like Python", { skip }, () => {
  const img = readPngMat(cv, new URL(ref.file, fixtures));
  const context = photoContext(cv, img);
  img.delete();
  try {
    for (const seq of ref.outlines) runSequence(seq, context, close);
  } finally {
    context.delete();
  }
});

test("edit_outline on the pipeline's own mask gives back runGrid's row exactly", { skip }, async () => {
  const bytes = readFileSync(new URL(ref.file, fixtures));
  const img = readPngMat(cv, new URL(ref.file, fixtures));
  const { rows: jsRows } = runGrid(cv, img, {
    sampleId: ref.sample_id, photo: ref.photo, imageId: await imageIdFor(ref.file, bytes), metadata: ref.metadata,
    processedAt: ref.processed_at,
  });
  const context = photoContext(cv, img);
  img.delete();
  const { labels, diff, band } = segmentGrid(cv, context.image, context.layout, context.pxPerMm, GRID_SEGMENT_DEFAULTS);
  diff.delete();
  band.delete();
  try {
    for (const row of jsRows) {
      const lbl = labels.intAt(Math.round(row.centroid_y_px), Math.round(row.centroid_x_px));
      const mask = cv.Mat.zeros(labels.rows, labels.cols, cv.CV_8UC1);
      labels.data32S.forEach((v, i) => { if (v === lbl) mask.data[i] = 1; });
      const contours = new cv.MatVector(), hierarchy = new cv.Mat();
      cv.findContours(mask, contours, hierarchy, cv.RETR_EXTERNAL, cv.CHAIN_APPROX_NONE);
      let outline = [];
      for (let i = 0; i < contours.size(); i++) {
        const c = contours.get(i);
        if (c.rows * 2 > outline.length) outline = Array.from(c.data32S);
        c.delete();
      }
      mask.delete(), contours.delete(), hierarchy.delete();
      const d = { particleRef: row.particle_ref, action: "edit_outline", reviewer: "DS", role: "expert",
        at: "2026-11-12T10:00:00Z", outline };
      const out = apply(row, d, context);
      for (const k of [...REMEASURED, "particle_id", "review_reason", "processed_at"]) {
        assert.ok(Object.is(out[k], row[k]), `${row.particle_ref} ${k}: ${out[k]} vs ${row[k]}`);
      }
      assert.equal(out.outline_edited, true);
      assert.equal(out.review_status, "corrected");
      assert.equal(row.outline_edited, false);
    }
  } finally {
    labels.delete();
    context.delete();
  }
});
