// Parity of the grid-crossing refinement and grid rectification with Python (fixture from dump_python_rectify.py).
// Skips when the pinned OpenCV.js hasn't been fetched: node web/scripts/fetch_opencv.mjs
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { findSheet, rectifyGrid, refineCrossings } from "../src/capture/sheet.js";
import { boxPoints } from "../src/capture/subpix.js";
import { loadOpenCVNode } from "./helpers.mjs";
import { readPngMat } from "./png_color.mjs";

const fixtures = new URL("fixtures/", import.meta.url);
const ref = JSON.parse(readFileSync(new URL("rectify.json", fixtures)));
const cv = await loadOpenCVNode();
const skip = cv ? false : "OpenCV.js not fetched (node web/scripts/fetch_opencv.mjs)";

/** Distances (px) of each crossing from Python's, sorted. */
function distances(ours, theirs) {
  return theirs.flatMap((row, r) => row.map(([x, y], c) => Math.hypot(ours[r][c][0] - x, ours[r][c][1] - y)))
    .sort((a, b) => a - b);
}

function worstPixel(grid, samples) {
  const n = grid.channels();
  let worst = 0;
  for (const [x, y, v] of samples) {
    v.forEach((p, k) => (worst = Math.max(worst, Math.abs(grid.data[(y * grid.cols + x) * n + k] - p))));
  }
  return worst;
}

for (const c of ref.cases) {
  const name = `${c.photo} (${c.layout.join(", ")}, ${c.pxPerMm} px/mm)`;

  test(`grid crossings and rectified grid match Python: ${name}`, { skip }, (t) => {
    const img = readPngMat(cv, new URL(c.photo, fixtures).pathname);
    const sheet = findSheet(cv, img);
    assert.deepEqual([sheet.layout.background, sheet.layout.paper], c.layout);
    assert.equal(sheet.pxPerMm, c.pxPerMm);
    // The refinement alone, from Python's homography (OpenCV.js 4.10 and cv2 5.0 fit it ~1e-7 apart).
    const same = distances(refineCrossings(cv, img, sheet.layout, c.homography, c.pxPerMm), c.crossings);
    const own = distances(sheet.crossings, c.crossings);
    const fmt = (d) => `max ${d.at(-1).toFixed(4)} px, median ${d[d.length >> 1].toExponential(1)} px`;
    t.diagnostic(`Python's homography: ${fmt(same)}; own homography: ${fmt(own)}`);
    if (c.unconverged === 0) {
      assert.ok(same.at(-1) < 0.05, `crossings from Python's homography: ${fmt(same)}`);
      assert.ok(own.at(-1) < 0.05, `crossings: ${fmt(own)}`);
    } else {
      // Python's cornerSubPix didn't converge on some corners, so its result there is chaotic, and it
      // reaches the other crossings through the smooth fit. Only the bulk can agree.
      t.diagnostic(`${c.unconverged} corners did not converge in Python`);
      for (const d of [same, own]) {
        assert.ok(d[d.length >> 1] < 0.05 && d.at(-1) < 2.5, `crossings: ${fmt(d)}`);
      }
    }

    // Rectification from the same crossings.
    const grid = rectifyGrid(cv, { ...sheet, crossings: c.crossings }, img);
    assert.deepEqual([grid.cols, grid.rows], c.gridSize);
    const worst = worstPixel(grid, c.samples);
    grid.delete();
    t.diagnostic(`rectified grid from Python's crossings: up to ${worst} grey levels off`);
    assert.ok(worst <= 1, `rectified grid pixels differ by up to ${worst} grey levels`);
    if (c.unconverged === 0) {
      const ownGrid = rectifyGrid(cv, sheet, img);
      const ownWorst = worstPixel(ownGrid, c.samples);
      ownGrid.delete();
      t.diagnostic(`rectified grid from own crossings: up to ${ownWorst} grey levels off`);
      assert.ok(ownWorst <= 2, `rectified grid pixels differ by up to ${ownWorst} grey levels`);
    }
    img.delete();
  });
}

test("boxPoints matches cv2.boxPoints", () => {
  // cv2.boxPoints(((100.5, 50.25), (30, 8), 33)) with OpenCV 5.0.0
  const want = [[85.741386, 45.435097], [90.098503, 38.725731], [115.258614, 55.064903], [110.901497, 61.774269]];
  boxPoints([[100.5, 50.25], [30, 8], 33]).forEach(([x, y], i) => {
    assert.ok(Math.abs(x - want[i][0]) < 1e-5 && Math.abs(y - want[i][1]) < 1e-5, `corner ${i}: ${x}, ${y}`);
  });
});
