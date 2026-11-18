// Part 8: the app shell. Processing works; the screens are planned.
// Screens: print a background -> upload photos -> run (in the browser) -> review -> export.
// Processing runs on the user's machine; Cloudflare Pages only serves these files.
import { imageIdFor, runGrid } from "./pipeline.js";
import { particlesCsv, summaryCsv } from "./export/csv.js";

export { particlesCsv, summaryCsv };

/**
 * Run one photo through parts 1-5 in the browser.
 * `imageData` is a canvas ImageData (RGBA); `file` the uploaded File (for its name and hash).
 * Returns {rows, problems, quality, run} (see pipeline.js runGrid), or throws with a message
 * for the user when the photo has no printed MIPPR sheet.
 */
export async function processPhoto(cv, imageData, file, { sampleId, photo, metadata, lineMm } = {}) {
  const imageId = await imageIdFor(file.name, await file.arrayBuffer());
  const rgba = cv.matFromImageData(imageData);
  const bgr = new cv.Mat();
  try {
    cv.cvtColor(rgba, bgr, cv.COLOR_RGBA2BGR);
    return runGrid(cv, bgr, { sampleId, photo, imageId, metadata, lineMm });
  } finally {
    rgba.delete();
    bgr.delete();
  }
}
