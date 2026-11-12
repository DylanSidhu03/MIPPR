// Parity of marker detection and sheet rectification with Python's cv2.aruco (fixture from dump_python_markers.py).
// Skips when the pinned OpenCV.js hasn't been fetched: node web/scripts/fetch_opencv.mjs
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { detectMarkers, findSheet, rectifySheet } from "../src/capture/sheet.js";
import { loadOpenCVNode, readGrayPng } from "./helpers.mjs";

const fixtures = new URL("fixtures/", import.meta.url);
const ref = JSON.parse(readFileSync(new URL("markers.json", fixtures)));
const cv = await loadOpenCVNode();
const skip = cv ? false : "OpenCV.js not fetched (node web/scripts/fetch_opencv.mjs)";

function photoMat(c) {
  const { width, height, data } = readGrayPng(new URL(c.photo, fixtures));
  const mat = new cv.Mat(height, width, cv.CV_8UC1);
  mat.data.set(data);
  if (c.blank) {
    const [x0, y0, x1, y1] = c.blank;
    for (let y = Math.max(0, y0); y < y1; y++) mat.data.fill(255, y * width + Math.max(0, x0), y * width + x1);
  }
  return mat;
}

function apply(H, x, y) {
  const z = H[6] * x + H[7] * y + H[8];
  return [(H[0] * x + H[1] * y + H[2]) / z, (H[3] * x + H[4] * y + H[5]) / z];
}

for (const c of ref.cases) {
  const name = `${c.photo}${c.blank ? " with one marker covered" : ""}`;

  test(`markers match cv2.aruco: ${name}`, { skip }, () => {
    const img = photoMat(c);
    const found = detectMarkers(cv, img);
    img.delete();
    assert.deepEqual(Object.keys(found), Object.keys(c.markers));
    for (const [id, corners] of Object.entries(c.markers)) {
      corners.forEach(([x, y], j) => {
        const d = Math.hypot(found[id][j][0] - x, found[id][j][1] - y);
        assert.ok(d < 1e-3, `marker ${id} corner ${j} is ${d} px from Python`);
      });
    }
  });

  test(`sheet and rectification match Python: ${name}`, { skip }, () => {
    const img = photoMat(c);
    const sheet = findSheet(cv, img);
    assert.deepEqual([sheet.layout.background, sheet.layout.paper], c.layout);
    assert.equal(sheet.pxPerMm, c.pxPerMm);
    assert.equal(sheet.markersFound, c.markersFound);
    // Compared where the sheet is: at the marker corners, which span it.
    for (const [x, y] of Object.values(c.markers).flat()) {
      const [ax, ay] = apply(sheet.homography, x, y);
      const [bx, by] = apply(c.homography, x, y);
      const d = Math.hypot(ax - bx, ay - by);
      assert.ok(d < 0.01, `homography maps photo (${x}, ${y}) ${d} px away from Python's`);
    }
    const rect = rectifySheet(cv, sheet, img);
    assert.deepEqual([rect.cols, rect.rows], c.rectifiedSize);
    let worst = 0;
    for (const [x, y, v] of c.samples) worst = Math.max(worst, Math.abs(rect.data[y * rect.cols + x] - v));
    assert.ok(worst <= 1, `rectified pixels differ by up to ${worst} grey levels`);
    rect.delete();
    img.delete();
  });
}

test("too few markers gives a readable error", { skip }, () => {
  const blank = new cv.Mat(400, 300, cv.CV_8UC1, new cv.Scalar(255));
  assert.throws(() => findSheet(cv, blank), /No MIPPR sheet markers/);
  blank.delete();
});
