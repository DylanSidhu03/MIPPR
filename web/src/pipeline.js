// One photo on a printed MIPPR sheet -> particle rows, in the browser. The JS twin of
// pipeline/mippr/cli.py run_grid: same steps, same settings, same output columns.
import { findSheet, rectifyGrid, whiteBalance } from "./capture/sheet.js";
import { checkQuality, measureQuality } from "./capture/quality.js";
import { GRID_SEGMENT_DEFAULTS, segmentGrid } from "./segmentation/grid.js";
import { buildRows } from "./export/csv.js";
import { balance, makeMeasureContext, measureWith } from "./review/context.js";

export const APP_VERSION = "0.1.0"; // pipeline/mippr/__init__.py __version__

/** "name-1a2b3c4d": the file name plus the first 8 hex digits of its SHA-1, as the Python pipeline does. */
export async function imageIdFor(fileName, bytes) {
  const digest = new Uint8Array(await crypto.subtle.digest("SHA-1", bytes));
  const hex = Array.from(digest.slice(0, 4), (b) => b.toString(16).padStart(2, "0")).join("");
  return `${fileName.replace(/\.[^./\\]+$/, "")}-${hex}`;
}

export function pictureLabel(sampleId, photo) {
  return `${sampleId}-P${String(Math.trunc(photo)).padStart(2, "0")}`;
}

/** Outline polygons (grid px) of one labelled particle, from a crop round its bounding box. */
function outlineOf(cv, labels, m) {
  const { x, y, w, h } = m._px;
  const x0 = Math.max(0, x - 1), y0 = Math.max(0, y - 1);
  const x1 = Math.min(labels.cols, x + w + 1), y1 = Math.min(labels.rows, y + h + 1);
  const mask = new cv.Mat(y1 - y0, x1 - x0, cv.CV_8UC1);
  const L = labels.data32S;
  for (let r = y0; r < y1; r++) {
    for (let c = x0; c < x1; c++) mask.data[(r - y0) * (x1 - x0) + (c - x0)] = L[r * labels.cols + c] === m.particle ? 1 : 0;
  }
  const contours = new cv.MatVector();
  const hier = new cv.Mat();
  cv.findContours(mask, contours, hier, cv.RETR_EXTERNAL, cv.CHAIN_APPROX_SIMPLE);
  const polys = [];
  for (let i = 0; i < contours.size(); i++) {
    const c = contours.get(i);
    const pts = [];
    for (let j = 0; j < c.data32S.length; j += 2) pts.push([c.data32S[j] + x0, c.data32S[j + 1] + y0]);
    polys.push(pts);
    c.delete();
  }
  mask.delete(), contours.delete(), hier.delete();
  return polys;
}

/** The white-balanced grid as RGBA pixels, for drawing on a canvas. */
function displayImage(balanced) {
  const { rows: h, cols: w } = balanced;
  const rgba = new Uint8ClampedArray(w * h * 4);
  const src = balanced.data;
  for (let i = 0, j = 0; i < src.length; i += 3, j += 4) {
    rgba[j] = src[i + 2], rgba[j + 1] = src[i + 1], rgba[j + 2] = src[i], rgba[j + 3] = 255;
  }
  return { width: w, height: h, rgba };
}

/**
 * Run parts 1-5 on one photo (a CV_8UC3 BGR Mat) and return
 * {rows, problems, quality, run}. Throws if no sheet is found, with the other photo
 * problems appended to the message, like the Python pipeline.
 * `imageId` should come from imageIdFor(); `processedAt` defaults to now (UTC, seconds).
 * With `forDisplay`, also returns `display` (the white-balanced grid as RGBA) and `outlines`
 * (each row's outline polygons in grid px, in the same order as `rows`). With `keepContext`, also
 * returns `context`: what measure() was given, so the review screen can re-measure a redrawn
 * outline (review/corrections.js); the caller owns it and calls `context.delete()`.
 */
export function runGrid(cv, img, {
  sampleId = "sample", photo = 1, imageId, metadata = {}, lineMm = null, params = {}, forDisplay = false, keepContext = false,
  processedAt = new Date().toISOString().replace(/\.\d+Z$/, "+00:00"),
} = {}) {
  const p = { ...GRID_SEGMENT_DEFAULTS, ...params };
  let sheet;
  try {
    sheet = findSheet(cv, img);
  } catch (e) {
    const others = checkQuality(cv, img).filter((q) => q.code !== "no_markers" && q.code !== "marker_missing");
    throw new Error([e.message, ...others.map((q) => `photo check: ${q.message}`)].join("\n"));
  }
  const quality = measureQuality(cv, img, sheet);
  const problems = checkQuality(cv, img, sheet, { metrics: quality });
  const lay = sheet.layout, ppm = sheet.pxPerMm;
  const mats = [];
  const keep = (m) => (mats.push(m), m);
  try {
    const rect = keep(rectifyGrid(cv, sheet, img));
    const { gains, report: wb } = whiteBalance(cv, sheet, img);
    const balanced = keep(balance(cv, rect, gains));
    const { labels, diff, band: segBand } = segmentGrid(cv, rect, lay, ppm, p);
    keep(labels), keep(diff), keep(segBand);
    const context = makeMeasureContext(cv, { rect, balanced, diff, layout: lay, pxPerMm: ppm, params: p, lineMm });
    mats.splice(0, mats.length, labels, segBand); // rect, balanced and diff now belong to the context
    if (!keepContext) mats.push(context); // context.delete() frees its Mats
    const { mmPerPx, scaleCorrected: corrected } = context;
    const measured = measureWith(context, labels);
    const label = pictureLabel(sampleId, photo);
    const rows = buildRows(measured, {
      sampleId, pictureLabel: label, imageId, metadata, appVersion: APP_VERSION, mmPerPx, processedAt,
      backgroundType: lay.background, scaleSource: corrected ? "user_corrected" : "markers",
      scaleFlag: corrected || sheet.markersFound < 4,
    });
    const run = {
      mode: "grid", sample_id: sampleId, picture_label: label, ...metadata, background_type: lay.background,
      paper: lay.paper, layout: { box_mm: lay.boxMm, line_mm: lay.lineMm, rows: lay.rows, cols: lay.cols },
      markers_found: sheet.markersFound, px_per_mm: ppm, mm_per_px: mmPerPx, printed_line_mm: lineMm,
      white_balance: wb, quality: { problems: problems.map((q) => q.asDict()), metrics: quality }, params: p,
    };
    const out = { rows, problems, quality, run, measured };
    if (forDisplay) {
      out.display = displayImage(balanced);
      out.outlines = [...measured].sort((a, b) => a.particle - b.particle).map((m) => outlineOf(cv, labels, m));
    }
    if (keepContext) out.context = context;
    return out;
  } finally {
    for (const m of mats) m.delete();
  }
}
