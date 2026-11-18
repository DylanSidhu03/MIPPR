// Part 8: browser port of pipeline/mippr/export.py: the rows of particles.csv and summary.csv (docs/OUTPUT_CSV.md),
// and CSV text written the way Python's csv module writes them, so files from the app and the Python pipeline are
// byte for byte the same. Parity with the Python reference is checked by web/tests/export.test.mjs.
import { COLOR_CLASSES, COLOR_RULES_VERSION } from "../color/rules.js";
import { MORPHOLOGY_CLASSES, morphologyRules } from "../morphology/rules.js";

export const NOTE = "Visual classification only. Whether a particle is plastic, and its polymer type, were not tested.";

// Flag thresholds (docs/OUTPUT_CSV.md section 7).
export const SIEVE_MM = 0.5;
export const NEAR_CUTOFF = 0.1; // +-10% around the sieve size
export const LOW_CONTRAST = 100.0; // provisional
export const MERGED_SOLIDITY = 0.75; // provisional
export const SIZE_UNCERTAIN = 0.1; // provisional: relative change in length between the 40% and 60% edges
export const CURVED_RATIO = 1.1; // centre-line length / straight length above which a particle counts as bent

export const SIZE_BINS = Object.freeze([[0.0, 0.5, "<0.5"], [0.5, 1.0, "0.5-1"], [1.0, 2.0, "1-2"], [2.0, 5.0, "2-5"],
  [5.0, Infinity, ">5"]].map((b) => Object.freeze(b)));
export const FLAGS = Object.freeze(["flag_edge", "flag_merged", "flag_low_confidence", "flag_scale",
  "flag_near_cutoff", "flag_min_width", "flag_low_contrast", "flag_line", "flag_multi_blob",
  "flag_width_unresolved", "flag_size_uncertain", "flag_bundle"]);
export const METADATA = Object.freeze(["date", "operator", "lab", "setup", "site"]);

export const COLUMNS = Object.freeze([
  "sample_id", "picture_label", "image_id", "photo_file", "particle_id", "particle_ref", "crop_file", ...METADATA,
  "centroid_x_px", "centroid_y_px", "bbox_x_px", "bbox_y_px", "bbox_w_px", "bbox_h_px",
  "centroid_x_mm", "centroid_y_mm",
  "length_mm", "width_mm", "area_mm2", "perimeter_mm", "ced_mm", "fiber_length_mm", "size_length_source",
  "size_class",
  "length_mm_outer", "length_mm_inner", "width_mm_outer", "width_mm_inner", "size_uncertainty",
  "convex_area_mm2", "convex_perimeter_mm",
  "aspect_ratio", "circularity", "solidity", "roundness", "major_mm", "minor_mm",
  "feret_ratio", "perimeter_subpixel_mm", "circularity_subpixel", "solidity_subpixel",
  "color_L", "color_a", "color_b", "color_L_sd", "color_a_sd", "color_b_sd", "color_hex",
  "color_R", "color_G", "color_B", "color_H", "color_S", "color_V",
  "opacity", "color_secondary", "color_secondary_fraction", "color_label", "color_confidence",
  "morphology_label", "morphology_source", "morphology_confidence", "morphology_runner_up",
  "morphology_runner_up_confidence",
  ...FLAGS, "review_reason",
  "review_status", "color_label_original", "morphology_label_original", "outline_edited", "derived_from", "tar_like",
  "reviewed_by", "reviewer_role", "reviewed_at",
  "polymer_confirmed", "polymer_method",
  "background_type", "mm_per_px", "scale_source",
  "app_version", "color_rules_version", "model_version", "processed_at",
]);

export const SUMMARY_COLUMNS = Object.freeze([
  "sample_id", "n_images", "n_particles",
  ...MORPHOLOGY_CLASSES.map((m) => `count_${m}`),
  ...COLOR_CLASSES.map((c) => `count_color_${c}`),
  ...SIZE_BINS.map((b) => `count_size_${b[2]}`),
  "length_mm_median", "length_mm_min", "length_mm_max",
  "n_reviewed", "n_corrected", "pct_human_confirmed",
  ...FLAGS.map((f) => `n_${f}`),
  "app_version", "color_rules_version", "model_version",
]);

// Columns that hold Python ints, written without a decimal point; every other number is a Python float.
export const INTEGER_COLUMNS = Object.freeze(new Set(["bbox_x_px", "bbox_y_px", "bbox_w_px", "bbox_h_px",
  ...SUMMARY_COLUMNS.filter((c) => c === "n_images" || c === "n_particles" || c.startsWith("count_")
    || (c.startsWith("n_") && c !== "n_particles"))]));

/** `m[k]`, or `fallback` when the key is missing (Python's dict.get). */
function get(m, k, fallback = null) {
  return m[k] === undefined ? fallback : m[k];
}

function isNone(v) {
  return v === null || v === undefined;
}

function roundHalfEven(x) {
  const r = Math.round(x);
  return r - x === 0.5 && r % 2 ? r - 1 : r;
}

/** Python's round(x, 1) on a float: correctly rounded, ties to even. */
function pyRound1(x) {
  const r = Number(x.toFixed(1)); // exact decimal rounding, but ties go up
  const v = x * 10;
  return Math.abs(v % 1) === 0.5 && v / 10 === x ? roundHalfEven(v) / 10 : r;
}

/** numpy's round(x, 1) (round(np.float64, 1) in the pipeline): rint(x * 10) / 10. */
function npRound1(x) {
  return roundHalfEven(x * 10) / 10;
}

/** Python's max(a, b): the first unless the second is larger (so NaN doesn't spread as in Math.max). */
function pyMax(a, b) {
  return b > a ? b : a;
}

/** Python's repr() of a float: the shortest round-trip digits, fixed notation for 1e-4 <= |x| < 1e16. */
export function pyFloat(x) {
  if (Number.isNaN(x)) return "nan";
  if (x === Infinity) return "inf";
  if (x === -Infinity) return "-inf";
  if (x === 0) return Object.is(x, -0) ? "-0.0" : "0.0";
  const sign = x < 0 ? "-" : "";
  const [mant, exp] = Math.abs(x).toExponential().split("e");
  const digits = mant.replace(".", "");
  const decpt = Number(exp) + 1; // the value is 0.<digits> * 10 ** decpt
  if (decpt > -4 && decpt <= 16) {
    if (decpt <= 0) return `${sign}0.${"0".repeat(-decpt)}${digits}`;
    if (decpt >= digits.length) return `${sign}${digits}${"0".repeat(decpt - digits.length)}.0`;
    return `${sign}${digits.slice(0, decpt)}.${digits.slice(decpt)}`;
  }
  const e = decpt - 1;
  const m = digits.length > 1 ? `${digits[0]}.${digits.slice(1)}` : digits;
  return `${sign}${m}e${e < 0 ? "-" : "+"}${String(Math.abs(e)).padStart(2, "0")}`;
}

export function sizeClass(lengthMm) {
  for (const [lo, hi, name] of SIZE_BINS) if (lo <= lengthMm && lengthMm < hi) return name;
  return "";
}

/** (length with the edge at 40% - length at 60%) / length at 50%; null without the edge check. */
export function sizeUncertainty(m) {
  if (isNone(get(m, "length_um_outer")) || !m.feret_max_um) return null;
  return (m.length_um_outer - m.length_um_inner) / m.feret_max_um;
}

/** True/false quality flags for one measured particle. Empty where not available yet. */
export function flags(m, scaleFlag = false, multiBlob = false) {
  const length = m.feret_max_um / 1000;
  const width = m.feret_min_um / 1000;
  const su = sizeUncertainty(m);
  const unresolved = Boolean(get(m, "width_unresolved"));
  const contrast = get(m, "_contrast");
  return {
    flag_edge: Boolean(get(m, "_touches_edge")),
    flag_merged: m.solidity < MERGED_SOLIDITY,
    flag_low_confidence: "", // needs colour rules (v2) or the morphology model (v3)
    flag_scale: Boolean(scaleFlag),
    flag_near_cutoff: SIEVE_MM * (1 - NEAR_CUTOFF) <= length && length <= SIEVE_MM * (1 + NEAR_CUTOFF),
    flag_min_width: width < SIEVE_MM && !unresolved, // a fiber too thin to measure has no known width
    flag_low_contrast: !isNone(contrast) && contrast < LOW_CONTRAST,
    flag_line: Boolean(get(m, "_touches_line")),
    flag_multi_blob: Boolean(multiBlob),
    flag_width_unresolved: unresolved,
    flag_size_uncertain: su === null ? "" : su > SIZE_UNCERTAIN,
    flag_bundle: "", // set by a reviewer; later by the model (v3)
  };
}

/** Every flag that is true, without the `flag_` prefix, separated by semicolons (e.g. `edge;min_width`). */
export function reviewReason(f) {
  return Object.entries(f).filter(([k, v]) => k.startsWith("flag_") && v === true).map(([k]) => k.slice(5)).join(";");
}

/**
 * {label, source, confidence, runnerUp, runnerUpConfidence} from the v2 rules. The fiber rule uses the straight
 * (Feret) length:width, or the along-the-fiber one for a particle that bends, so a curved fiber still counts.
 */
export function morphology(m) {
  let ar = m.feret_ratio;
  if (get(m, "fiber_uniform") && get(m, "fiber_width_um") && m.fiber_length_um >= CURVED_RATIO * m.feret_max_um) {
    ar = pyMax(ar, m.fiber_length_um / m.fiber_width_um);
  }
  const r = morphologyRules(ar, m.circularity, m.solidity_subpixel, get(m, "opacity"), Boolean(get(m, "width_unresolved")));
  return { label: r.label, source: "rule", confidence: r.confidence, runnerUp: r.runnerUp,
    runnerUpConfidence: r.runnerUpConfidence };
}

function hex(m) {
  return "#" + ["R", "G", "B"].map((c) => Math.max(0, Math.min(255, roundHalfEven(m[`${c}_mean`])))
    .toString(16).padStart(2, "0")).join("");
}

/**
 * {ids: Map(measurement index -> particle_id), multi: Set of boxes holding several blobs}. The box label (B4);
 * B4-1, B4-2 ... when a box holds several blobs, numbered top to bottom, then left to right.
 */
export function particleIds(measurements) {
  const byBox = new Map();
  measurements.forEach((m, i) => {
    const box = get(m, "box") || "";
    if (!byBox.has(box)) byBox.set(box, []);
    byBox.get(box).push(i);
  });
  const ids = new Map();
  const multi = new Set();
  for (const [box, idx] of byBox) {
    const key = (i) => [roundHalfEven(measurements[i].y_um), measurements[i].x_um];
    idx.sort((i, j) => {
      const [a, b] = [key(i), key(j)];
      return a[0] - b[0] || a[1] - b[1];
    });
    idx.forEach((i, n) => ids.set(i, !box ? String(n + 1) : idx.length === 1 ? box : `${box}-${n + 1}`));
    if (box && idx.length > 1) multi.add(box);
  }
  return { ids, multi };
}

function sizeRange(m) {
  if (isNone(get(m, "length_um_outer"))) return {};
  const unresolved = get(m, "width_unresolved");
  return {
    length_mm_outer: m.length_um_outer / 1000, length_mm_inner: m.length_um_inner / 1000,
    width_mm_outer: unresolved ? "" : m.width_um_outer / 1000,
    width_mm_inner: unresolved ? "" : m.width_um_inner / 1000,
    size_uncertainty: sizeUncertainty(m),
  };
}

/**
 * Per-particle rows, named, ordered and filled as in docs/OUTPUT_CSV.md, from measure() output (Python's keys).
 * `backgroundType` is the printed sheet's; `scaleSource` is `markers`, `paper_edges` or `user_corrected`.
 */
export function buildRows(measurements, { sampleId, pictureLabel, imageId, metadata = {}, appVersion, mmPerPx,
  processedAt, backgroundType, scaleSource = "markers", scaleFlag = false, photoFile = "", cropDir = "" }) {
  const { ids, multi } = particleIds(measurements);
  const order = measurements.map((_, i) => i).sort((i, j) => measurements[i].particle - measurements[j].particle);
  return order.map((i) => {
    const m = measurements[i];
    const f = flags(m, scaleFlag, multi.has(get(m, "box")));
    const px = m._px;
    const length = m.feret_max_um / 1000;
    const morph = morphology(m);
    const fiber = morph.label === "fiber";
    const fiberLength = fiber ? m.fiber_length_um / 1000 : "";
    const sizeLength = fiber ? pyMax(length, fiberLength) : length; // along the fiber for fibers
    const row = Object.fromEntries(COLUMNS.map((c) => [c, ""]));
    Object.assign(row, {
      sample_id: sampleId, picture_label: pictureLabel, image_id: imageId, photo_file: photoFile,
      particle_id: ids.get(i), particle_ref: `${pictureLabel}-${ids.get(i)}`,
      crop_file: cropDir ? `${cropDir}/${pictureLabel}-${ids.get(i)}.png` : "",
      ...Object.fromEntries(METADATA.map((k) => [k, get(metadata, k, "") || ""])),
      centroid_x_px: npRound1(px.cx), centroid_y_px: npRound1(px.cy),
      bbox_x_px: px.x, bbox_y_px: px.y, bbox_w_px: px.w, bbox_h_px: px.h,
      centroid_x_mm: m.x_um / 1000, centroid_y_mm: m.y_um / 1000,
      length_mm: length, width_mm: get(m, "width_unresolved") ? "" : m.feret_min_um / 1000,
      area_mm2: m.area_um2 / 1e6, perimeter_mm: m.perimeter_um / 1000,
      ced_mm: m.ced_um / 1000, fiber_length_mm: fiberLength,
      size_length_source: fiber ? "fiber_length" : "max_feret", size_class: sizeClass(sizeLength),
      ...sizeRange(m),
      convex_area_mm2: m.convex_area_um2 / 1e6, convex_perimeter_mm: m.convex_perimeter_um / 1000,
      aspect_ratio: m.aspect_ratio, circularity: m.circularity, solidity: m.solidity,
      roundness: m.roundness, major_mm: m.major_um / 1000, minor_mm: m.minor_um / 1000,
      feret_ratio: m.feret_ratio, perimeter_subpixel_mm: m.perimeter_subpixel_um / 1000,
      circularity_subpixel: m.circularity_subpixel, solidity_subpixel: m.solidity_subpixel,
      color_L: m.L_mean, color_a: m.a_mean, color_b: m.b_mean,
      color_L_sd: m.L_sd, color_a_sd: m.a_sd, color_b_sd: m.b_sd, color_hex: hex(m),
      ...Object.fromEntries([..."RGBHSV"].map((c) => [`color_${c}`, m[`${c}_mean`]])),
      opacity: isNone(get(m, "opacity")) ? "" : m.opacity,
      color_secondary: get(m, "color_secondary", ""),
      color_secondary_fraction: get(m, "color_secondary_fraction", ""),
      // Provisional colour rules (color/rules.js): their thresholds aren't fitted to labelled particles yet.
      color_label: get(m, "color_label", ""), color_confidence: get(m, "color_confidence", ""),
      morphology_label: morph.label, morphology_source: morph.source, morphology_confidence: morph.confidence,
      morphology_runner_up: morph.runnerUp, morphology_runner_up_confidence: morph.runnerUpConfidence,
      ...f,
      review_reason: reviewReason(f),
      review_status: "auto", outline_edited: false, tar_like: "",
      background_type: backgroundType, mm_per_px: mmPerPx, scale_source: scaleSource,
      app_version: appVersion, color_rules_version: get(m, "color_label") ? COLOR_RULES_VERSION : "",
      processed_at: processedAt,
    });
    return row;
  });
}

function counter(values) {
  const c = new Map();
  for (const v of values) c.set(v, (c.get(v) || 0) + 1);
  return c;
}

function median(values) {
  const s = [...values].sort((a, b) => a - b);
  const n = s.length;
  return n % 2 ? s[(n - 1) / 2] : (s[n / 2 - 1] + s[n / 2]) / 2;
}

/** One row per sample, from particle rows only. Rejected particles are left out. */
export function buildSummary(rows) {
  const out = [];
  for (const sid of new Set(rows.map((r) => r.sample_id))) {
    const mine = rows.filter((r) => r.sample_id === sid);
    const kept = mine.filter((r) => r.review_status !== "rejected");
    const s = Object.fromEntries(SUMMARY_COLUMNS.map((c) => [c, ""]));
    Object.assign(s, { sample_id: sid, n_images: new Set(mine.map((r) => r.image_id)).size, n_particles: kept.length });
    // The label columns already hold the reviewer's correction (the prediction moves to *_original).
    for (const [col, names, prefix] of [["morphology_label", MORPHOLOGY_CLASSES, "count_"],
      ["color_label", COLOR_CLASSES, "count_color_"]]) {
      const labels = kept.map((r) => r[col]).filter((v) => v !== "");
      if (labels.length) { // counts stay empty until the labels exist (v2 colour, v3 morphology)
        const c = counter(labels);
        for (const n of names) s[`${prefix}${n}`] = c.get(n) || 0;
      }
    }
    const sizes = counter(kept.map((r) => r.size_class));
    for (const b of SIZE_BINS) s[`count_size_${b[2]}`] = sizes.get(b[2]) || 0;
    // The size used for classes: along the fiber for fibers, max Feret otherwise.
    const lengths = kept.map((r) => (r.size_length_source === "fiber_length" ? pyMax(r.length_mm, r.fiber_length_mm)
      : r.length_mm));
    if (lengths.length) {
      s.length_mm_median = median(lengths);
      s.length_mm_min = lengths.reduce((a, b) => (b < a ? b : a));
      s.length_mm_max = lengths.reduce((a, b) => (b > a ? b : a));
    }
    const human = kept.filter((r) => r.review_status === "confirmed" || r.review_status === "corrected").length;
    Object.assign(s, {
      n_reviewed: mine.filter((r) => r.review_status !== "auto").length,
      n_corrected: mine.filter((r) => r.review_status === "corrected").length,
      pct_human_confirmed: kept.length ? pyRound1((100 * human) / kept.length) : "",
    });
    for (const f of FLAGS) {
      if (f !== "flag_low_confidence" && f !== "flag_bundle") s[`n_${f}`] = kept.filter((r) => r[f] === true).length;
    }
    for (const v of ["app_version", "color_rules_version", "model_version"]) {
      s[v] = [...new Set(mine.filter((r) => r[v] !== "").map((r) => String(r[v])))].sort().join(";");
    }
    out.push(s);
  }
  return out;
}

function cell(v, column, intColumns) {
  if (isNone(v)) return "";
  if (v === true) return "True";
  if (v === false) return "False";
  if (typeof v === "number") return intColumns.has(column) && Number.isInteger(v) ? String(v) : pyFloat(v);
  return String(v);
}

function quote(s) {
  return /[",\r\n]/.test(s) ? `"${s.replaceAll('"', '""')}"` : s;
}

/**
 * CSV text as Python's csv.DictWriter writes it (header, QUOTE_MINIMAL, \r\n line ends): booleans as True/False,
 * null as empty, numbers in `intColumns` as integers and all other numbers as Python floats.
 */
export function toCsv(rows, columns, intColumns = INTEGER_COLUMNS) {
  const line = (cells) => (cells.length === 1 && cells[0] === "" ? '""' : cells.map(quote).join(","));
  const lines = [line([...columns])];
  for (const r of rows) {
    const extra = Object.keys(r).filter((k) => !columns.includes(k));
    if (extra.length) throw new Error(`toCsv: row has keys that are not columns: ${extra.join(", ")}`);
    lines.push(line(columns.map((c) => cell(r[c], c, intColumns))));
  }
  return lines.map((l) => `${l}\r\n`).join("");
}

/** particles.csv with exactly the columns in docs/OUTPUT_CSV.md. */
export function particlesCsv(rows) {
  return toCsv(rows, COLUMNS);
}

/** summary.csv, calculated from the particle rows; rejected rows are left out. */
export function summaryCsv(rows) {
  return toCsv(buildSummary(rows), SUMMARY_COLUMNS);
}

/** The NOTE.txt statement. */
export function noteTxt() {
  return `${NOTE}\n`;
}
