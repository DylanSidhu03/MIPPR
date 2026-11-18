// Part 5: the v3 model's inputs (morphology/model.js) against Python's training/common.py (model_input).
// Fixture from dump_python_model_input.py. No ONNX Runtime needed: only the input building and the output reading.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { buildInputs, checkSidecar, featureVector, flattenOnGrey, fromLogits, imageTensor, prepareImage,
  softmax } from "../src/morphology/model.js";

const ref = JSON.parse(readFileSync(new URL("fixtures/model_input.json", import.meta.url)));

test("crop on grey, resized: within one grey level of Python's prepare_image", () => {
  for (const c of ref.images) {
    const crop = { width: c.width, height: c.height, rgba: Uint8ClampedArray.from(c.rgba) };
    const got = prepareImage(crop, c.size, ref.grey);
    let worst = 0, off = 0;
    for (let i = 0; i < got.length; i++) {
      const d = Math.abs(got[i] - c.rgb[i]);
      worst = Math.max(worst, d);
      off += d > 0;
    }
    assert.ok(worst <= 1, `${c.width}x${c.height}: max difference ${worst}`);
    assert.ok(off / got.length < 0.1, `${c.width}x${c.height}: ${off} of ${got.length} values differ`);
  }
});

test("flattening on grey is exact where no resize is needed", () => {
  const c = ref.images.find((im) => im.width === im.size && im.height === im.size);
  const flat = flattenOnGrey({ width: c.width, height: c.height, rgba: c.rgba }, ref.grey);
  assert.deepEqual(Array.from(flat.rgb), c.rgb);
});

test("shape values: transformed, normalised, missing -> 0, background one-hot, as Python", () => {
  for (const { row, vector } of ref.features) {
    const got = Array.from(featureVector(row, ref.sidecar));
    assert.equal(got.length, vector.length);
    got.forEach((v, i) => assert.ok(Math.abs(v - vector[i]) < 1e-5, `${JSON.stringify(row)} [${i}]: ${v} vs ${vector[i]}`));
  }
});

test("image tensor is channels first and normalised", () => {
  const rgb = Uint8Array.from([255, 0, 128, 0, 255, 0, 0, 0, 255, 51, 102, 153]); // 2 x 2
  const t = imageTensor(rgb, 2, [0.5, 0.5, 0.5], [0.25, 0.25, 0.25]);
  assert.equal(t.length, 12);
  assert.ok(Math.abs(t[0] - 2) < 1e-6); // R of pixel 0
  assert.ok(Math.abs(t[4] - -2) < 1e-6); // G of pixel 0
  assert.ok(Math.abs(t[11] - (0.6 - 0.5) / 0.25) < 1e-6); // B of pixel 3
});

test("buildInputs and reading the logits", () => {
  const sidecar = { format: "mippr-morphology-model", format_version: 1, classes: ["fragment", "rubbery_fragment", "foam"],
    crop_size: 8, grey: 128, image_mean: [0.5, 0.5, 0.5], image_std: [0.25, 0.25, 0.25], model_version: "morphology-test",
    ...ref.sidecar };
  checkSidecar(sidecar);
  const c = ref.images[1];
  const inputs = buildInputs({ width: c.width, height: c.height, rgba: c.rgba }, ref.features[0].row, sidecar);
  assert.equal(inputs.image.length, 3 * 8 * 8);
  assert.equal(inputs.features.length, ref.features[0].vector.length);
  assert.equal(inputs.scale, c.width / 8);
  const r = fromLogits([0.1, 2.0, 1.5], sidecar);
  assert.equal(r.label, "rubbery_fragment");
  assert.equal(r.runnerUp, "foam");
  assert.equal(r.modelVersion, "morphology-test");
  assert.ok(r.confidence > r.runnerUpConfidence);
  assert.ok(Math.abs(softmax([1, 1]).reduce((a, b) => a + b) - 1) < 1e-12);
  assert.throws(() => checkSidecar({ format: "other" }));
});
