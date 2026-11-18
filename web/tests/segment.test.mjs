// Parity of the grid segmentation with Python's segment_grid (fixtures from dump_python_segment.py).
// The input is the grid already flattened by Python, so only part 2 is compared.
// Skips when the pinned OpenCV.js hasn't been fetched: node web/scripts/fetch_opencv.mjs
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { Layout } from "../src/capture/sheet.js";
import { GRID_SEGMENT_DEFAULTS, boxOf, segmentGrid } from "../src/segmentation/grid.js";
import { loadOpenCVNode } from "./helpers.mjs";
import { readPng } from "./png_color_segment.mjs";

const fixtures = new URL("fixtures/", import.meta.url);
const ref = JSON.parse(readFileSync(new URL("segment.json", fixtures)));
const cv = await loadOpenCVNode();
const skip = cv ? false : "OpenCV.js not fetched (node web/scripts/fetch_opencv.mjs)";

const camel = (s) => s.replace(/_(.)/g, (_, c) => c.toUpperCase());

test("defaults match GridSegmentParams", () => {
  assert.deepEqual(Object.fromEntries(Object.entries(ref.params).map(([k, v]) => [camel(k), v])), { ...GRID_SEGMENT_DEFAULTS });
});

function gridMat(file) {
  const { width, height, channels, data } = readPng(new URL(file, fixtures));
  assert.equal(channels, 3);
  const mat = new cv.Mat(height, width, cv.CV_8UC3);
  for (let i = 0; i < data.length; i += 3) [mat.data[i], mat.data[i + 1], mat.data[i + 2]] = [data[i + 2], data[i + 1], data[i]];
  return mat;
}

const segmented = new Map();
function segment(c) {
  if (!segmented.has(c.name)) {
    const layout = new Layout({ background: c.layout[0], paper: c.layout[1] });
    const img = gridMat(c.grid);
    const out = segmentGrid(cv, img, layout, c.pxPerMm);
    img.delete();
    const res = {
      layout,
      labels: Int32Array.from(out.labels.data32S),
      diff: Float32Array.from(out.diff.data32F),
      band: Uint8Array.from(out.band.data),
      size: [out.labels.cols, out.labels.rows],
    };
    Object.values(out).forEach((m) => m.delete());
    segmented.set(c.name, res);
  }
  return segmented.get(c.name);
}

for (const c of ref.cases) {
  test(`same particles, boxes and masks as Python: ${c.name}`, { skip }, () => {
    const { layout, labels, band, size } = segment(c);
    assert.deepEqual(size, c.size);
    const want = readPng(new URL(c.labels, fixtures)).data;
    const n = c.particles.length;
    assert.equal(labels.reduce((a, b) => Math.max(a, b), 0), n);
    const [w] = size;
    for (const p of c.particles) {
      let inter = 0, union = 0, sx = 0, sy = 0, area = 0, touches = false;
      for (let i = 0; i < labels.length; i++) {
        const a = labels[i] === p.label, b = want[i] === p.label;
        inter += a && b;
        union += a || b;
        if (a) {
          area++;
          sx += i % w;
          sy += Math.floor(i / w);
          touches ||= band[i] === 1;
        }
      }
      const iou = inter / union;
      assert.ok(iou >= 0.99, `${c.name} ${p.box}: IoU ${iou}`);
      assert.equal(layout.boxLabel(...boxOf(layout, c.pxPerMm, sx / area, sy / area)), p.box);
      assert.equal(touches, p.touchesBand, `${c.name} ${p.box}: touches the line band`);
    }
    let differ = 0;
    for (let i = 0; i < labels.length; i++) differ += labels[i] !== want[i];
    assert.equal(differ, 0, `${differ} label pixels differ from Python`);
  });

  test(`difference map and line band match Python: ${c.name}`, { skip }, () => {
    const { diff, band } = segment(c);
    const wantBand = readPng(new URL(c.band, fixtures)).data;
    for (let i = 0; i < band.length; i++) if (band[i] * 255 !== wantBand[i]) assert.fail(`band differs at pixel ${i}`);
    const wantDiff = readPng(new URL(c.diff, fixtures)).data;
    let worst = 0;
    for (let i = 0; i < diff.length; i++) worst = Math.max(worst, Math.abs(Math.min(255, diff[i]) - wantDiff[i]));
    assert.ok(worst <= 1, `difference map (rounded) is up to ${worst} grey levels from Python`);
    const [w] = c.size;
    let exact = 0;
    for (const [x, y, v] of c.diffSamples) exact = Math.max(exact, Math.abs(diff[y * w + x] - v));
    assert.ok(exact < 0.01, `sampled difference values are up to ${exact} from Python`);
  });
}

test("boxOf clips to the grid", () => {
  const lay = new Layout();
  const ppm = 10;
  assert.deepEqual(boxOf(lay, ppm, 0, 0), [0, 0]);
  assert.deepEqual(boxOf(lay, ppm, 125, 245), [2, 1]);
  assert.deepEqual(boxOf(lay, ppm, -5, 1e6), [lay.rows - 1, 0]);
});
