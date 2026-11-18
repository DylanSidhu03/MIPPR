// Part 6: applying a reviewer's decisions to particle rows. The JS twin of pipeline/mippr/review/corrections.py,
// ported line by line (same rules, statuses, error messages and review order); parity is checked by
// web/tests/review.test.mjs.
//
// Rows are objects with the particles.csv columns; values read back from a CSV ("True", "0.5") are accepted.
// Functions never change their inputs: they return new rows. A decision is a plain object:
// {particleRef, action, reviewer, role, at, colorLabel = "", morphologyLabel = "", outline = [], tags = {}}.
import { COLOR_CLASSES } from "../color/rules.js";
import { MORPHOLOGY_CLASSES } from "../morphology/rules.js";
import { FLAGS, METADATA, buildRows, flags, reviewReason } from "../export/csv.js";
import { APP_VERSION } from "../pipeline.js";
import { measureWith } from "./context.js";

export const STATUSES = Object.freeze(["auto", "confirmed", "corrected", "rejected"]);
export const ACTIONS = Object.freeze(["confirm", "reject", "relabel", "edit_outline", "split", "merge", "tag"]);
export const ROLES = Object.freeze(["expert", "community"]);
export const TAGS = Object.freeze(["tar_like", "flag_bundle"]);
// A reviewer may also say a colour can't be told (OUTPUT_CSV.md 4.6, color_confidence).
export const REVIEW_COLORS = Object.freeze([...COLOR_CLASSES, "unknown"]);
export const REVIEW_MORPHOLOGIES = Object.freeze([...MORPHOLOGY_CLASSES]);

// Columns a re-measurement takes from the new outline: everything measured, derived or predicted from it.
export const REMEASURED = Object.freeze([
  "centroid_x_px", "centroid_y_px", "bbox_x_px", "bbox_y_px", "bbox_w_px", "bbox_h_px",
  "centroid_x_mm", "centroid_y_mm",
  "length_mm", "width_mm", "area_mm2", "perimeter_mm", "ced_mm", "fiber_length_mm", "size_length_source",
  "size_class", "length_mm_outer", "length_mm_inner", "width_mm_outer", "width_mm_inner", "size_uncertainty",
  "convex_area_mm2", "convex_perimeter_mm",
  "aspect_ratio", "circularity", "solidity", "roundness", "major_mm", "minor_mm",
  "feret_ratio", "perimeter_subpixel_mm", "circularity_subpixel",
  "color_L", "color_a", "color_b", "color_L_sd", "color_a_sd", "color_b_sd", "color_hex",
  "color_R", "color_G", "color_B", "color_H", "color_S", "color_V",
  "opacity", "color_secondary", "color_secondary_fraction",
  "color_label", "color_confidence", "color_rules_version",
  "morphology_label", "morphology_source", "morphology_confidence", "morphology_runner_up",
  "morphology_runner_up_confidence",
  ...FLAGS.filter((f) => f !== "flag_low_confidence" && f !== "flag_bundle"),
  "mm_per_px", "app_version",
]);
// The prediction columns kept as they are when a reviewer has already corrected that label.
export const COLOR_PREDICTION = Object.freeze(["color_label", "color_confidence"]);
export const MORPHOLOGY_PREDICTION = Object.freeze(["morphology_label", "morphology_source", "morphology_confidence",
  "morphology_runner_up", "morphology_runner_up_confidence"]);

/** A decision from Python's Decision fields (snake_case, e.g. dataclasses.asdict), with its defaults. */
export function decisionFromPython(d) {
  return {
    particleRef: d.particle_ref, action: d.action, reviewer: d.reviewer, role: d.role, at: d.at,
    colorLabel: d.color_label ?? "", morphologyLabel: d.morphology_label ?? "", outline: d.outline ?? [],
    tags: d.tags ?? {},
  };
}

function isTrue(v) {
  return v === true || v === "True";
}

function isEmpty(v) {
  return v === "" || v === null || v === undefined;
}

/** Python's float(v), or `fallback` where it would raise. */
function toFloat(v, fallback = null) {
  if (typeof v === "number") return v;
  if (typeof v === "boolean") return Number(v);
  if (typeof v !== "string") return fallback;
  const s = v.trim();
  if (/^[+-]?(inf|infinity)$/i.test(s)) return s[0] === "-" ? -Infinity : Infinity;
  if (/^[+-]?nan$/i.test(s)) return NaN;
  const digits = String.raw`\d(?:_?\d)*`;
  if (!new RegExp(`^[+-]?(?:${digits}(?:\\.(?:${digits})?)?|\\.${digits})(?:[eE][+-]?${digits})?$`).test(s)) return fallback;
  return Number(s.replaceAll("_", ""));
}

/** Python's repr() of the values in messages: strings, lists, null, numbers and booleans. */
function repr(v) {
  if (v === null || v === undefined) return "None";
  if (v === true) return "True";
  if (v === false) return "False";
  if (Array.isArray(v)) return `[${v.map(repr).join(", ")}]`;
  if (typeof v !== "string") return String(v);
  const q = v.includes("'") && !v.includes('"') ? '"' : "'";
  const body = [...v].map((ch) => {
    if (ch === "\\" || ch === q) return `\\${ch}`;
    if (ch === "\n") return "\\n";
    if (ch === "\r") return "\\r";
    if (ch === "\t") return "\\t";
    const c = ch.codePointAt(0);
    return c < 0x20 || c === 0x7f ? `\\x${c.toString(16).padStart(2, "0")}` : ch;
  }).join("");
  return `${q}${body}${q}`;
}

function daysFromCivil(y, m, d) {
  y -= m <= 2 ? 1 : 0;
  const era = Math.floor(y / 400);
  const yoe = y - era * 400;
  const doy = Math.floor((153 * (m + (m > 2 ? -3 : 9)) + 2) / 5) + d - 1;
  return era * 146097 + yoe * 365 + Math.floor(yoe / 4) - Math.floor(yoe / 100) + doy - 719468;
}

const isLeap = (y) => (y % 4 === 0 && y % 100 !== 0) || y % 400 === 0;
const monthDays = (y, m) => [31, isLeap(y) ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1];

/** Days since 1970-01-01 of an ISO date (YYYY-MM-DD, YYYYMMDD, YYYY-Www[-D], YYYYWww[D]), or null. */
function isoDate(s) {
  let g = /^(\d{4})(-?)(\d{2})\2(\d{2})$/.exec(s);
  if (g) {
    const [y, m, d] = [+g[1], +g[3], +g[4]];
    if (y < 1 || m < 1 || m > 12 || d < 1 || d > monthDays(y, m)) return null;
    return daysFromCivil(y, m, d);
  }
  g = /^(\d{4})(-?)W(\d{2})(?:\2(\d))?$/.exec(s);
  if (!g) return null;
  const [y, w, d] = [+g[1], +g[3], g[4] === undefined ? 1 : +g[4]];
  const jan1 = (((daysFromCivil(y, 1, 1) + 3) % 7) + 7) % 7; // 0 = Monday
  const weeks = jan1 === 3 || (jan1 === 2 && isLeap(y)) ? 53 : 52;
  if (y < 1 || w < 1 || w > weeks || d < 1 || d > 7) return null;
  const week1 = daysFromCivil(y, 1, 4) - ((((daysFromCivil(y, 1, 4) + 3) % 7) + 7) % 7);
  return week1 + (w - 1) * 7 + d - 1;
}

/** Microseconds of a time (HH[[:]MM[[:]SS]][.ffffff]), or null; fractions are truncated to 6 digits. */
function isoTime(s) {
  const g = /^(\d{2})(?:(:?)(\d{2})(?:\2(\d{2}))?)?(?:[.,](\d+))?$/.exec(s);
  if (!g) return null;
  const [h, m, sec] = [+g[1], +(g[3] ?? 0), +(g[4] ?? 0)];
  if (h > 23 || m > 59 || sec > 59) return null;
  const frac = BigInt((g[5] ?? "").slice(0, 6).padEnd(6, "0"));
  return BigInt((h * 60 + m) * 60 + sec) * 1000000n + frac;
}

/** Where the date ends, as Python's datetime._find_isoformat_datetime_separator decides it. */
function dateLength(s) {
  const digit = (i) => /\d/.test(s[i] ?? "");
  if (s.length === 7) return 7;
  if (s[4] === "-") {
    if (s[5] !== "W") return 10;
    if (s.length > 8 && s[8] === "-") return s.length > 10 && digit(10) ? 8 : 10;
    return 8;
  }
  if (s[4] !== "W") return 8;
  let i = 7;
  while (i < s.length && digit(i)) i++;
  if (i < 9) return i;
  return i % 2 === 0 ? 7 : 8;
}

/**
 * An ISO 8601 time as microseconds since 1970-01-01 UTC (a BigInt; a time without a zone is taken as UTC).
 * Accepts what Python's datetime.fromisoformat accepts once "Z" is read as "+00:00".
 */
export function parseTime(at) {
  const s = String(at).replaceAll("Z", "+00:00");
  const bad = () => new Error(`Review time ${repr(at)} is not ISO 8601.`);
  if (s.length < 7) throw bad();
  const n = dateLength(s);
  const days = isoDate(s.slice(0, n));
  if (days === null) throw bad();
  let micros = BigInt(days) * 86400000000n;
  if (s.length > n) {
    const rest = s.slice(n + 1);
    const z = rest.includes("-") ? rest.indexOf("-") : rest.indexOf("+");
    const t = isoTime(z < 0 ? rest : rest.slice(0, z));
    if (t === null) throw bad();
    micros += t;
    if (z >= 0) {
      const off = isoTime(rest.slice(z + 1));
      if (off === null || off >= 86400000000n) throw bad();
      micros += rest[z] === "+" ? -off : off;
    }
  }
  return micros;
}

function check(row, d) {
  if (!ACTIONS.includes(d.action)) {
    throw new Error(`Unknown review action ${repr(d.action)}; expected one of ${ACTIONS.join(", ")}.`);
  }
  if (d.particleRef !== row.particle_ref) {
    throw new Error(`Decision for ${repr(d.particleRef)} applied to row ${repr(row.particle_ref)}.`);
  }
  if (!String(d.reviewer).trim()) throw new Error("A decision needs a reviewer.");
  if (!ROLES.includes(d.role)) throw new Error(`Unknown reviewer role ${repr(d.role)}; expected expert or community.`);
  parseTime(d.at);
  const color = d.colorLabel ?? "", morph = d.morphologyLabel ?? "";
  if (d.action === "relabel") {
    if (!color && !morph) throw new Error("relabel needs a colour or a morphology label.");
    if (color && !REVIEW_COLORS.includes(color)) throw new Error(`Unknown colour class ${repr(color)}.`);
    if (morph && !REVIEW_MORPHOLOGIES.includes(morph)) throw new Error(`Unknown morphology class ${repr(morph)}.`);
  }
  if (d.action === "tag") {
    const tags = d.tags ?? {};
    const bad = Object.keys(tags).filter((k) => !TAGS.includes(k));
    if (bad.length || !Object.keys(tags).length) {
      throw new Error(`Unknown or missing tags ${repr(bad)}; expected some of ${TAGS.join(", ")}.`);
    }
    if (Object.values(tags).some((v) => typeof v !== "boolean")) throw new Error("Tag values must be True or False.");
  }
}

/** confirmed, or corrected when a label or the outline differs from what the pipeline produced. */
function status(row) {
  const changed = !isEmpty(row.color_label_original) || !isEmpty(row.morphology_label_original)
    || isTrue(row.outline_edited);
  return changed ? "corrected" : "confirmed";
}

/** Set a label; keep the prediction in *_original on the first correction only. */
function relabel(row, col, value) {
  const orig = `${col}_original`;
  if (value === row[col]) return;
  if (isEmpty(row[orig])) row[orig] = row[col];
  else if (value === row[orig]) row[orig] = ""; // back to the prediction: no longer a correction
  row[col] = value;
}

function reasonOf(row) {
  return reviewReason(Object.fromEntries(FLAGS.map((f) => [f, isTrue(row[f])])));
}

/**
 * The row after one decision. The input row is not changed.
 *
 * - confirm: the labels are right (status confirmed, or corrected if earlier corrections stand)
 * - reject: a false detection; the row stays in particles.csv, status rejected
 * - relabel: new colour and/or morphology label (status corrected)
 * - edit_outline: `decision.outline` is re-measured with `context` (context.js, for the row's photo) and
 *   outline_edited is set (status corrected)
 * - tag: `tar_like` / `flag_bundle` set to true or false; the status is not changed
 * - split, merge: not built yet (throws, with name NotImplementedError)
 *
 * Every decision records reviewed_by, reviewer_role and reviewed_at (the latest decision wins).
 */
export function apply(row, decision, context = null) {
  const d = decision;
  check(row, d);
  if (d.action === "split" || d.action === "merge") {
    const e = new Error(
      `${d.action} is not built yet: it turns one row into two (or two into one), which needs rules for the `
      + "new particle_ids and for the row that is merged away. remeasure() already measures any mask, so it "
      + "can be built on that once those rules are decided.");
    e.name = "NotImplementedError";
    throw e;
  }
  let out = { ...row };
  if (d.action === "edit_outline") {
    if (context === null || context === undefined) {
      throw new Error("edit_outline needs the photo's MeasureContext to re-measure the outline.");
    }
    if (d.outline === null || d.outline === undefined || d.outline.length < 3) {
      throw new Error("edit_outline needs a polygon of at least 3 points.");
    }
    out = remeasure(out, d.outline, context);
  } else if (d.action === "relabel") {
    if (d.colorLabel) relabel(out, "color_label", d.colorLabel);
    if (d.morphologyLabel) relabel(out, "morphology_label", d.morphologyLabel);
  } else if (d.action === "tag") {
    Object.assign(out, d.tags);
    out.review_reason = reasonOf(out);
  }
  if (d.action === "reject") out.review_status = "rejected";
  else if (d.action !== "tag") out.review_status = status(out);
  Object.assign(out, { reviewed_by: d.reviewer, reviewer_role: d.role, reviewed_at: d.at });
  return out;
}

function roundHalfEven(x) {
  const r = Math.round(x);
  return r - x === 0.5 && r % 2 ? r - 1 : r;
}

/**
 * The 0/1 mask (Int32Array, `width` x `height`) of a polygon: [[x, y], ...] or [x, y, x, y, ...] with vertices
 * at pixel centres, as OpenCV contours are. A {width, height, data} mask of the same size is copied as is.
 */
export function outlineMask(cv, outline, width, height) {
  if (outline && !Array.isArray(outline) && outline.data && outline.width === width && outline.height === height) {
    return Int32Array.from(outline.data, (v) => (v ? 1 : 0));
  }
  const flat = Array.from(outline).flat(Infinity).map(Number);
  if (flat.length % 2) throw new Error("An outline is a list of (x, y) points.");
  if (flat.length < 6) throw new Error("An outline needs at least 3 points.");
  const pts = cv.matFromArray(flat.length / 2, 1, cv.CV_32SC2, flat.map(roundHalfEven));
  const polys = new cv.MatVector();
  polys.push_back(pts);
  const m = cv.Mat.zeros(height, width, cv.CV_8UC1);
  try {
    cv.fillPoly(m, polys, new cv.Scalar(1));
    if (!cv.countNonZero(m)) throw new Error("The outline covers no pixels of the image.");
    return Int32Array.from(m.data);
  } finally {
    m.delete();
    polys.delete();
    pts.delete();
  }
}

/**
 * The row with every measured, derived and predicted value recomputed from an edited outline.
 *
 * `outline` is a polygon in the rectified image's px (or a mask, see outlineMask) and `context` the photo's
 * context (context.js); given the same inputs as the pipeline, the result equals the pipeline's row for that mask.
 * Kept from the row: identifiers (particle_id stays the box label even if the centroid moved), sample details,
 * background type, scale source, processed_at, review columns and reviewer tags, and any label a reviewer
 * already corrected (with its confidence and source). Sets outline_edited; review_status is left for apply().
 */
export function remeasure(row, outline, context) {
  const { cv } = context;
  const { cols: width, rows: height } = context.image;
  const labels = { width, height, channels: 1, data: outlineMask(cv, outline, width, height) };
  const [m] = measureWith(context, labels);
  const scaleFlag = isTrue(row.flag_scale);
  const [fresh] = buildRows([m], {
    sampleId: row.sample_id, pictureLabel: row.picture_label, imageId: row.image_id,
    metadata: Object.fromEntries(METADATA.map((k) => [k, row[k] ?? ""])), appVersion: APP_VERSION,
    mmPerPx: context.mmPerPx, processedAt: row.processed_at ?? "", backgroundType: row.background_type ?? "",
    scaleSource: row.scale_source ?? "", scaleFlag,
  });
  // flag_multi_blob depends on the other particles in the box, so it comes from the row.
  Object.assign(fresh, flags(m, scaleFlag, isTrue(row.flag_multi_blob)));
  const out = { ...row };
  for (const k of REMEASURED) out[k] = fresh[k];
  if (!isEmpty(row.color_label_original)) for (const k of COLOR_PREDICTION) out[k] = row[k];
  if (!isEmpty(row.morphology_label_original)) for (const k of MORPHOLOGY_PREDICTION) out[k] = row[k];
  out.outline_edited = true;
  out.review_reason = reasonOf(out);
  return out;
}

/**
 * All decisions applied in time order (ties keep their given order). Returns new rows in the same order.
 * `contexts` maps image_id to that photo's context (a Map or an object), needed for edit_outline.
 */
export function applyAll(rows, decisions, contexts = null) {
  const index = new Map();
  rows.forEach((r, i) => {
    if (index.has(r.particle_ref)) throw new Error(`Two rows share particle_ref ${repr(r.particle_ref)}.`);
    index.set(r.particle_ref, i);
  });
  const out = rows.map((r) => ({ ...r }));
  const timed = decisions.map((d) => [parseTime(d.at), d]);
  timed.sort((a, b) => (a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0));
  const contextOf = (id) => (contexts instanceof Map ? contexts.get(id) : contexts?.[id]) ?? null;
  for (const [, d] of timed) {
    if (!index.has(d.particleRef)) throw new Error(`No particle ${repr(d.particleRef)} for this decision.`);
    const i = index.get(d.particleRef);
    out[i] = apply(out[i], d, contextOf(out[i].image_id));
  }
  return out;
}

/** Rows that count in summary.csv: everything not rejected (buildSummary does the same). */
export function kept(rows) {
  return rows.filter((r) => r.review_status !== "rejected");
}

function lowestConfidence(row) {
  const confs = [toFloat(row.color_confidence), toFloat(row.morphology_confidence)].filter((c) => c !== null);
  return confs.length ? confs.reduce((a, b) => (b < a ? b : a)) : 1.0;
}

/**
 * Rows in the order a reviewer should see them. Returns a new array; the rows are not copied.
 *
 * 1. not yet reviewed and flagged (any flag in review_reason, or flag_low_confidence)
 * 2. not yet reviewed, not flagged
 * 3. already confirmed or corrected
 * 4. rejected
 * Within the first two groups the lowest colour or morphology confidence comes first, since the
 * flag_low_confidence threshold isn't decided yet; otherwise the input order is kept.
 */
export function reviewQueue(rows) {
  const key = (r) => {
    const s = r.review_status || "auto";
    if (s === "rejected") return [3, 0.0];
    if (s !== "auto") return [2, 0.0];
    const flagged = Boolean(r.review_reason) || isTrue(r.flag_low_confidence);
    return [flagged ? 0 : 1, lowestConfidence(r)];
  };
  const lt = (a, b) => a[0] < b[0] || (a[0] === b[0] && a[1] < b[1]);
  return rows.map((r) => [key(r), r]).sort((a, b) => (lt(a[0], b[0]) ? -1 : lt(b[0], a[0]) ? 1 : 0)).map(([, r]) => r);
}
