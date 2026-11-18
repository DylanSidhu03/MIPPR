// The review screen's outline geometry (src/review/edit.js). Skipped when OpenCV.js hasn't been fetched.
import assert from "node:assert/strict";
import { test } from "node:test";
import { contoursOf, cutPieces, mergedOutline, pathOutline, polygonsMask } from "../src/review/edit.js";
import { loadOpenCVNode } from "./helpers.mjs";

const cv = await loadOpenCVNode();
const skip = cv ? false : "OpenCV.js not fetched (node web/scripts/fetch_opencv.mjs)";
const W = 40, H = 30;
const area = (m) => m.reduce((s, v) => s + v, 0);

test("polygon mask and contours", { skip }, () => {
  const m = polygonsMask(cv, [[[5, 5], [14, 5], [14, 14], [5, 14]]], W, H);
  assert.equal(area(m), 100);
  assert.equal(contoursOf(cv, m, W, H).length, 1);
});

test("a line across cuts a particle in two; one beside it doesn't", { skip }, () => {
  const m = polygonsMask(cv, [[[5, 5], [24, 5], [24, 14], [5, 14]]], W, H);
  const pieces = cutPieces(cv, m, W, H, [15, 8], [15, 10]); // short stroke, extended across
  assert.equal(pieces.length, 2);
  const a = pieces.map((p) => area(polygonsMask(cv, [p], W, H)));
  assert.ok(a.every((v) => v >= 70) && a[0] + a[1] <= 200); // about half each, less the 2 px cut
  assert.equal(cutPieces(cv, m, W, H, [30, 0], [30, 29]).length, 1);
  assert.equal(cutPieces(cv, m, W, H, [15, 8], [15, 8]).length, 0);
});

test("merged outline spans both particles", { skip }, () => {
  const a = polygonsMask(cv, [[[2, 2], [6, 2], [6, 6], [2, 6]]], W, H);
  const b = polygonsMask(cv, [[[20, 20], [24, 20], [24, 24], [20, 24]]], W, H);
  const hull = polygonsMask(cv, [mergedOutline(cv, [a, b], W, H)], W, H);
  assert.ok(hull[4 * W + 4] && hull[22 * W + 22] && hull[13 * W + 13]);
});

test("hand-drawn path", () => {
  assert.equal(pathOutline([[0, 0], [0.5, 0.5], [1, 1]]), null);
  assert.deepEqual(pathOutline([[0, 0], [5, 0], [5, 5], [5.2, 5.1]]), [[0, 0], [5, 0], [5, 5]]);
});
