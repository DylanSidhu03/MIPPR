// Part 5: browser port of pipeline/mippr/morphology/model.py. Planned; nothing here is implemented yet.
// Must give the same results as the Python reference (checked by the parity tests, see web/README.md).

/**
 * ONNX Runtime Web session for the exported v3 model
 */
export function loadModel(url) {
  throw new Error("Part 5: loadModel is not implemented yet");
}

/**
 * Class probabilities -> {label, confidence, runnerUp, ...}
 */
export function predict(session, crop, features, backgroundType) {
  throw new Error("Part 5: predict is not implemented yet");
}
