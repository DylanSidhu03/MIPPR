// Parity of the JS sheet layout with pipeline/mippr/capture/sheet.py (fixture from dump_python_layout.py).
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { BACKGROUNDS, LAYOUT_VERSION, Layout, PAPERS, layoutFromMarkerIds } from "../src/capture/sheet.js";

const ref = JSON.parse(readFileSync(new URL("fixtures/layouts.json", import.meta.url)));
const TOL = 1e-6; // mm

function close(actual, expected, path) {
  if (Array.isArray(expected)) {
    assert.equal(actual.length, expected.length, `${path}: length`);
    expected.forEach((e, i) => close(actual[i], e, `${path}[${i}]`));
  } else if (typeof expected === "object" && expected !== null) {
    assert.deepEqual(Object.keys(actual).sort(), Object.keys(expected).sort(), `${path}: keys`);
    for (const k of Object.keys(expected)) close(actual[k], expected[k], `${path}.${k}`);
  } else if (typeof expected === "number") {
    assert.ok(Math.abs(actual - expected) <= TOL, `${path}: ${actual} vs ${expected}`);
  } else {
    assert.equal(actual, expected, path);
  }
}

test("constants match Python", () => {
  assert.equal(LAYOUT_VERSION, ref.layoutVersion);
  assert.deepEqual([...BACKGROUNDS], ref.backgrounds);
  assert.deepEqual(Object.fromEntries(Object.entries(PAPERS).map(([k, v]) => [k, [...v]])), ref.papers);
});

for (const r of ref.layouts) {
  const o = r.options;
  test(`layout ${o.background} ${o.paper} ${o.boxMm} mm boxes`, () => {
    const lay = new Layout(o);
    const name = `${o.background}/${o.paper}/${o.boxMm}`;
    close(lay.sizeMm, r.sizeMm, `${name}.sizeMm`);
    assert.equal(lay.cols, r.cols);
    assert.equal(lay.rows, r.rows);
    close(lay.gridOriginMm, r.gridOriginMm, `${name}.gridOriginMm`);
    close(lay.gridSizeMm, r.gridSizeMm, `${name}.gridSizeMm`);
    assert.deepEqual(lay.markerIds(), r.markerIds);
    close(lay.markerCornersMm(), r.markerCornersMm, `${name}.markerCornersMm`);
    const labels = Array.from({ length: lay.rows }, (_, i) => Array.from({ length: lay.cols }, (_, j) => lay.boxLabel(i, j)));
    assert.deepEqual(labels, r.boxLabels);
    close(lay.scaleLineMm(), r.scaleLineMm, `${name}.scaleLineMm`);
    close(lay.patchesMm(), r.patchesMm, `${name}.patchesMm`);
  });
}

test("marker IDs identify background and paper", () => {
  for (const [id, expected] of Object.entries(ref.layoutFromMarkerId)) {
    if (expected === null) {
      assert.throws(() => layoutFromMarkerIds([Number(id)]), /No MIPPR sheet markers/);
    } else {
      const lay = layoutFromMarkerIds([Number(id)]);
      assert.deepEqual([lay.background, lay.paper], expected, `id ${id}`);
      assert.ok(lay.equals(new Layout({ background: expected[0], paper: expected[1] })));
    }
  }
});

test("invalid layouts are rejected", () => {
  assert.throws(() => new Layout({ background: "grey_grid" }), /background must be one of/);
  assert.throws(() => new Layout({ paper: "a3" }), /paper must be one of/);
});
