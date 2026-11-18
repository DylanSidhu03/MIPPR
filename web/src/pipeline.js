// One photo on a printed MIPPR sheet -> particle rows, in the browser. The JS twin of
// pipeline/mippr/cli.py run_grid: same steps, same settings, same output columns.
import { findSheet, rectifyGrid, whiteBalance } from "./capture/sheet.js";
import { checkQuality, measureQuality } from "./capture/quality.js";
import { GRID_SEGMENT_DEFAULTS, backgroundImage, boxOf, lineBand, segmentGrid } from "./segmentation/grid.js";
import { measure } from "./measurement/geometry.js";
import { colorClasses } from "./color/rules.js";
import { buildRows } from "./export/csv.js";

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

/** The rectified grid scaled by the white-balance gains, clipped and truncated to 8 bits like numpy's astype. */
function applyGains(cv, rect, gains) {
  const out = new cv.Mat(rect.rows, rect.cols, cv.CV_8UC3);
  const src = rect.data, dst = out.data;
  for (let i = 0; i < src.length; i += 3) {
    for (let c = 0; c < 3; c++) dst[i + c] = Math.trunc(Math.min(255, Math.max(0, Math.fround(src[i + c]) * gains[c])));
  }
  return out;
}

/**
 * Run parts 1-5 on one photo (a CV_8UC3 BGR Mat) and return
 * {rows, problems, quality, run}. Throws if no sheet is found, with the other photo
 * problems appended to the message, like the Python pipeline.
 * `imageId` should come from imageIdFor(); `processedAt` defaults to now (UTC, seconds).
 */
export function runGrid(cv, img, {
  sampleId = "sample", photo = 1, imageId, metadata = {}, lineMm = null, params = {},
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
    const balanced = keep(applyGains(cv, rect, gains));
    const { labels, diff, band: segBand } = segmentGrid(cv, rect, lay, ppm, p);
    keep(labels), keep(diff), keep(segBand);
    // A particle "touches a line" if it reaches the masked band round a printed line; the
    // outer border band also means it may be cut off.
    const { band, outer } = lineBand(cv, lay, ppm, [labels.rows, labels.cols], p.lineMarginMm);
    keep(band);
    const nearLine = keep(new cv.Mat());
    const kernel = keep(cv.Mat.ones(3, 3, cv.CV_8U));
    cv.dilate(band, nearLine, kernel);
    let mmPerPx = 1.0 / ppm;
    const corrected = lineMm !== null && lineMm !== undefined && Math.abs(lineMm - 100.0) > 1e-9;
    if (corrected) mmPerPx *= lineMm / 100.0; // the printer scaled the sheet: every length is off by the same factor
    const bg = keep(backgroundImage(cv, balanced, lay, ppm, p.insetFrac));
    const measured = measure(cv, labels, rect, mmPerPx * 1000, diff, p.edgeFraction, Math.ceil(outer) + 2, {
      boxFn: (x, y) => lay.boxLabel(...boxOf(lay, ppm, x, y)),
      lineMask: nearLine,
      colorImg: balanced,
      bgImg: bg,
      colorClasses: (crop, mask, op) => colorClasses(cv, crop, mask, op),
    });
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
    return { rows, problems, quality, run, measured };
  } finally {
    for (const m of mats) m.delete();
  }
}
