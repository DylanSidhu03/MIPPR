// Upload limits (src/limits.js).
import assert from "node:assert/strict";
import { test } from "node:test";
import { MAX_FILE_MB, fileProblem, pixelProblem } from "../src/limits.js";

test("files and photos over the limits are refused with a message", () => {
  assert.equal(fileProblem({ type: "image/jpeg", size: 8e6 }), null);
  assert.match(fileProblem({ type: "image/jpeg", size: (MAX_FILE_MB + 1) * 1e6 }), /limit/);
  assert.match(fileProblem({ type: "application/pdf", size: 1e5 }), /not an image/);
  assert.equal(fileProblem({ type: "", size: 1e5 }), null); // some systems give no type
  assert.equal(pixelProblem(8000, 6000), null); // 48 MP phone photo
  assert.match(pixelProblem(10000, 8000), /80 megapixels/);
});
