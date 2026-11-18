// Part 6: what measure() was given for one photo, kept so an outline the reviewer redraws is measured
// exactly as the pipeline measured it. The JS twin of pipeline/mippr/review/corrections.py MeasureContext,
// built with the same steps as runGrid (pipeline.js) and cli.run_grid.
import { printerProblem, printerScale } from "../capture/printer.js";
import { findSheet, rectifyGrid, whiteBalance } from "../capture/sheet.js";
import { GRID_SEGMENT_DEFAULTS, backgroundImage, boxOf, lineBand, segmentGrid } from "../segmentation/grid.js";
import { measure } from "../measurement/geometry.js";
import { colorClasses } from "../color/rules.js";

/** The rectified grid scaled by the white-balance gains, clipped and truncated to 8 bits like numpy's astype. */
export function balance(cv, rect, gains) {
  const out = new cv.Mat(rect.rows, rect.cols, cv.CV_8UC3);
  const src = rect.data, dst = out.data;
  for (let i = 0; i < src.length; i += 3) {
    for (let c = 0; c < 3; c++) dst[i + c] = Math.trunc(Math.min(255, Math.max(0, Math.fround(src[i + c]) * gains[c])));
  }
  return out;
}

/**
 * The context for one photo from the pieces runGrid already has: `rect` (rectified grid, CV_8UC3), `balanced`
 * (white-balanced copy, used for colour), `diff` (segmentGrid's difference map), the sheet's `layout` and
 * `pxPerMm`, the segmentation `params` and the printed line's measured length `lineMm` (null if 100 mm).
 *
 * Fields, as Python's MeasureContext: image, mmPerPx, bgImg (Python's `background`), diff, colorImg, lineMask,
 * boxFn, edgeFraction, edgeMarginPx; plus cv, colorClasses (measure()'s option), layout, pxPerMm and
 * scaleCorrected. The context owns its Mats, including the three passed in: call delete() when done.
 */
export function makeMeasureContext(cv, { rect, balanced, diff, layout, pxPerMm, params = {}, lineMm = null }) {
  const p = { ...GRID_SEGMENT_DEFAULTS, ...params };
  // A particle "touches a line" if it reaches the masked band round a printed line; the outer border band
  // also means it may be cut off.
  const { band, outer } = lineBand(cv, layout, pxPerMm, [rect.rows, rect.cols], p.lineMarginMm);
  const lineMask = new cv.Mat();
  const kernel = cv.Mat.ones(3, 3, cv.CV_8U);
  cv.dilate(band, lineMask, kernel);
  band.delete();
  kernel.delete();
  const scaleCorrected = lineMm !== null && lineMm !== undefined && Math.abs(lineMm - 100.0) > 1e-9;
  let mmPerPx = 1.0 / pxPerMm;
  if (scaleCorrected) mmPerPx *= lineMm / 100.0; // the printer scaled the sheet: every length is off by the same factor
  return {
    cv,
    image: rect,
    mmPerPx,
    bgImg: backgroundImage(cv, balanced, layout, pxPerMm, p.insetFrac),
    diff,
    colorImg: balanced,
    lineMask,
    boxFn: (x, y) => layout.boxLabel(...boxOf(layout, pxPerMm, x, y)),
    edgeFraction: p.edgeFraction,
    edgeMarginPx: Math.ceil(outer) + 2,
    colorClasses: (crop, mask, op) => colorClasses(cv, crop, mask, op),
    layout,
    pxPerMm,
    scaleCorrected,
    delete() {
      for (const m of [this.image, this.bgImg, this.diff, this.colorImg, this.lineMask]) if (m && !m.isDeleted()) m.delete();
    },
  };
}

/** measure()'s options from a context (Python's MeasureContext.kwargs). */
export function measureOptions(ctx) {
  return { boxFn: ctx.boxFn, lineMask: ctx.lineMask, colorImg: ctx.colorImg, bgImg: ctx.bgImg,
    colorClasses: ctx.colorClasses };
}

/** measure() on a label image (Mat or {width, height, data}) with the context's inputs, as runGrid calls it. */
export function measureWith(ctx, labels) {
  return measure(ctx.cv, labels, ctx.image, ctx.mmPerPx * 1000, ctx.diff, ctx.edgeFraction, ctx.edgeMarginPx,
    measureOptions(ctx));
}

/**
 * The context for a photo (CV_8UC3 BGR Mat) on a printed sheet, from the same steps as runGrid.
 * For when the rows were made earlier (e.g. reopened from a CSV) and only the photo is at hand.
 * The scale is found the same way: an entered `lineMm` if given, else the printer's scale from the
 * paper's edges when it is off by more than 1%. Throws if no sheet is found.
 */
export function photoContext(cv, img, { params = {}, lineMm = null } = {}) {
  const p = { ...GRID_SEGMENT_DEFAULTS, ...params };
  const sheet = findSheet(cv, img);
  if (lineMm === null || lineMm === undefined) {
    const printer = printerScale(cv, sheet, img);
    if (printerProblem(printer)) lineMm = 100.0 * printer.scale;
  }
  const rect = rectifyGrid(cv, sheet, img);
  const { gains } = whiteBalance(cv, sheet, img);
  const balanced = balance(cv, rect, gains);
  const { labels, diff, band } = segmentGrid(cv, rect, sheet.layout, sheet.pxPerMm, p);
  labels.delete();
  band.delete();
  return makeMeasureContext(cv, { rect, balanced, diff, layout: sheet.layout, pxPerMm: sheet.pxPerMm, params: p, lineMm });
}
