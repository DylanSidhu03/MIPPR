// Part 5: the v3 morphology model in the browser, run with ONNX Runtime Web. The JS twin of
// pipeline/mippr/morphology/model.py (model_input) and training/common.py (the shape-value inputs).
//
// Not wired into the pipeline yet, and nothing here runs on import: v1/v2 work without a model.
// Only when a model is configured does the app call loadModel(url), which loads ONNX Runtime Web
// and the model file with its JSON sidecar (written by training/export_onnx.py); then
// predict(model, crop, row) for each particle.
//
// The model's inputs, as in training (the sidecar says which values):
// - `image`: float32 [1, 3, S, S]: the crop (crops.js cropParticle, background alpha 0) on neutral
//   grey, resized to S x S like cv2.resize INTER_AREA, RGB, (x / 255 - image_mean) / image_std;
// - `features`: float32 [1, F]: each shape value in sidecar.features transformed (log1p or none),
//   then (x - mean) / std, missing -> 0; then the background type one-hot (sidecar.backgrounds);
// - output `logits` [1, C] -> softmax -> label, confidence, runner-up (sidecar.classes).
//
// The image input matches Python's prepare_image within one grey level (OpenCV's resize rounds in
// fixed point); the shape values match exactly. Checked by web/tests/model.test.mjs.

export const SIDECAR_FORMAT = "mippr-morphology-model";
export const SIDECAR_VERSION = 1;
export const DEFAULT_GREY = 128;
// ONNX Runtime Web, served with the site like OpenCV.js (the site's CSP allows only 'self').
// Not vendored yet: put ort.min.js and its .wasm files in web/vendor/onnxruntime-web/ when the model ships.
export const ORT_LOCAL_DIR = "vendor/onnxruntime-web/";

/** The crop on grey: {width, height, rgb} from {width, height, rgba}, the same arithmetic as model_input. */
export function flattenOnGrey(crop, grey = DEFAULT_GREY) {
  const { width, height, rgba } = crop;
  const rgb = new Uint8Array(width * height * 3);
  for (let i = 0, j = 0; i < width * height; i++, j += 3) {
    const a = rgba[4 * i + 3] / 255.0;
    for (let c = 0; c < 3; c++) rgb[j + c] = Math.trunc(rgba[4 * i + c] * a + grey * (1 - a)); // numpy's astype(uint8)
  }
  return { width, height, rgb };
}

/** Area weights along one axis for shrinking n -> m pixels (cv2 INTER_AREA): [[src, weight], ...] per output. */
function areaTable(n, m) {
  const scale = n / m, tab = [];
  for (let d = 0; d < m; d++) {
    const f0 = d * scale, f1 = Math.min(f0 + scale, n), cell = f1 - f0, w = [];
    for (let s = Math.floor(f0); s < Math.ceil(f1 - 1e-9); s++) {
      const overlap = Math.min(s + 1, f1) - Math.max(s, f0);
      if (overlap > 1e-9) w.push([s, overlap / cell]);
    }
    tab.push(w);
  }
  return tab;
}

/**
 * Linear source positions along one axis for enlarging with INTER_AREA: OpenCV's "area mode", in which each
 * output pixel takes the source pixel it falls in, blending with the next only where a source edge crosses it.
 */
function linearTable(n, m) {
  const scale = n / m, inv = m / n, tab = [];
  for (let d = 0; d < m; d++) {
    let s = Math.floor(d * scale);
    let f = Math.fround(d + 1 - (s + 1) * inv);
    f = f <= 0 ? 0 : f - Math.floor(f);
    if (s < 0) { s = 0; f = 0; }
    if (s >= n - 1) { s = n - 1; f = 0; }
    const w0 = Math.round((1 - f) * 2048); // OpenCV's 11-bit fixed-point coefficients
    tab.push([[s, w0], [Math.min(s + 1, n - 1), 2048 - w0]]);
  }
  return tab;
}

/**
 * Resize an RGB image to size x size like cv2.resize(..., INTER_AREA): area averaging when shrinking
 * both ways, else OpenCV's linear "area mode" (linearTable). Within one grey level of OpenCV.
 */
export function resizeArea(rgb, width, height, size) {
  const out = new Uint8Array(size * size * 3);
  if (width >= size && height >= size) {
    const tx = areaTable(width, size), ty = areaTable(height, size);
    for (let y = 0; y < size; y++) {
      for (let x = 0; x < size; x++) {
        for (let c = 0; c < 3; c++) {
          let v = 0;
          for (const [sy, wy] of ty[y]) for (const [sx, wx] of tx[x]) v += wy * wx * rgb[3 * (sy * width + sx) + c];
          out[3 * (y * size + x) + c] = Math.min(255, Math.max(0, Math.round(v)));
        }
      }
    }
    return out;
  }
  const tx = linearTable(width, size), ty = linearTable(height, size);
  for (let y = 0; y < size; y++) {
    const [[y0, wy0], [y1, wy1]] = ty[y];
    for (let x = 0; x < size; x++) {
      const [[x0, wx0], [x1, wx1]] = tx[x];
      for (let c = 0; c < 3; c++) {
        const p = (yy, xx) => rgb[3 * (yy * width + xx) + c];
        const v = wy0 * (wx0 * p(y0, x0) + wx1 * p(y0, x1)) + wy1 * (wx0 * p(y1, x0) + wx1 * p(y1, x1));
        out[3 * (y * size + x) + c] = Math.min(255, (v + (1 << 21)) >> 22);
      }
    }
  }
  return out;
}

/** RGB uint8 size x size: Python's training/common.py prepare_image (model_input), in RGB order. */
export function prepareImage(crop, size, grey = DEFAULT_GREY) {
  const flat = flattenOnGrey(crop, grey);
  return resizeArea(flat.rgb, flat.width, flat.height, size);
}

/** float32 3 x size x size (channels first), (x / 255 - mean) / std per channel. */
export function imageTensor(rgb, size, mean, std) {
  const n = size * size, out = new Float32Array(3 * n);
  for (let i = 0; i < n; i++) for (let c = 0; c < 3; c++) out[c * n + i] = (rgb[3 * i + c] / 255 - mean[c]) / std[c];
  return out;
}

const TRANSFORMS = { none: (x) => x, log1p: (x) => Math.log1p(Math.max(x, 0)) };

/** float32 [F]: the shape values of a particles.csv row, normalised as the sidecar says, then the background one-hot. */
export function featureVector(row, sidecar) {
  const out = [];
  for (const f of sidecar.features) {
    const raw = row[f.name];
    const x = raw === "" || raw === null || raw === undefined ? NaN : Number(raw);
    const t = TRANSFORMS[f.transform];
    if (!t) throw new Error(`unknown feature transform ${f.transform}`);
    out.push(Number.isFinite(x) ? (t(x) - f.mean) / f.std : 0);
  }
  for (const b of sidecar.backgrounds) out.push(row.background_type === b ? 1 : 0);
  return Float32Array.from(out);
}

/** {image, features, scale}: the model's inputs for one particle (scale = crop px per input px, as model_input). */
export function buildInputs(crop, row, sidecar) {
  const size = sidecar.crop_size;
  const rgb = prepareImage(crop, size, sidecar.grey ?? DEFAULT_GREY);
  return { image: imageTensor(rgb, size, sidecar.image_mean, sidecar.image_std), features: featureVector(row, sidecar),
    scale: crop.width / size };
}

export function softmax(logits) {
  const m = Math.max(...logits), e = Array.from(logits, (v) => Math.exp(v - m)), s = e.reduce((a, b) => a + b, 0);
  return e.map((v) => v / s);
}

/** {label, confidence, runnerUp, runnerUpConfidence, modelVersion, probabilities} from logits. */
export function fromLogits(logits, sidecar) {
  const p = softmax(logits);
  const order = p.map((v, i) => i).sort((a, b) => p[b] - p[a] || a - b);
  const [a, b] = order;
  return { label: sidecar.classes[a], confidence: p[a], runnerUp: b === undefined ? "" : sidecar.classes[b],
    runnerUpConfidence: b === undefined ? 0 : p[b], modelVersion: sidecar.model_version,
    probabilities: Object.fromEntries(sidecar.classes.map((c, i) => [c, p[i]])) };
}

export function checkSidecar(sidecar) {
  if (sidecar?.format !== SIDECAR_FORMAT || sidecar.format_version !== SIDECAR_VERSION) {
    throw new Error(`not a MIPPR morphology model sidecar (format ${sidecar?.format} v${sidecar?.format_version})`);
  }
  for (const k of ["classes", "features", "backgrounds", "crop_size", "image_mean", "image_std", "model_version"]) {
    if (!(k in sidecar)) throw new Error(`model sidecar is missing ${k}`);
  }
  return sidecar;
}

/** ONNX Runtime Web: globalThis.ort if already there, else its script from the site (ORT_LOCAL_DIR). */
export function loadOrt({ dir = ORT_LOCAL_DIR } = {}) {
  if (globalThis.ort) return Promise.resolve(globalThis.ort);
  if (typeof document === "undefined") return Promise.reject(new Error("ONNX Runtime Web is not loaded"));
  return new Promise((resolve, reject) => {
    const s = document.createElement("script");
    s.src = `${dir}ort.min.js`;
    s.onload = () => {
      globalThis.ort.env.wasm.wasmPaths = dir;
      resolve(globalThis.ort);
    };
    s.onerror = () => reject(new Error(`could not load ${s.src}`));
    document.head.appendChild(s);
  });
}

/**
 * Load an exported model: the .onnx file and its sidecar (default `${modelUrl}.json`).
 * Call only when a model is configured. Returns {session, sidecar, ort} for predict().
 */
export async function loadModel(modelUrl, { sidecarUrl = `${modelUrl}.json`, ort = null } = {}) {
  const sidecar = checkSidecar(await (await fetch(sidecarUrl)).json());
  const rt = ort ?? (await loadOrt());
  const session = await rt.InferenceSession.create(modelUrl, { executionProviders: ["wasm"] });
  return { session, sidecar, ort: rt };
}

/**
 * Classify one particle: `crop` from crops.js cropParticle ({width, height, rgba}), `row` its particles.csv row
 * (shape values and background_type). -> {label, confidence, runnerUp, runnerUpConfidence, modelVersion, probabilities}
 */
export async function predict(model, crop, row) {
  const { session, sidecar, ort } = model;
  const s = sidecar.crop_size;
  const { image, features } = buildInputs(crop, row, sidecar);
  const out = await session.run({ image: new ort.Tensor("float32", image, [1, 3, s, s]),
    features: new ort.Tensor("float32", features, [1, features.length]) });
  return fromLogits(Array.from(out.logits.data), sidecar);
}
