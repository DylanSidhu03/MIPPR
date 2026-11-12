// Part 8: the app shell. Planned.
// Screens: print a background -> upload photos -> run (in the browser) -> review -> export.
// Processing runs on the user's machine; Cloudflare Pages only serves these files.
import { findSheet, rectifyGrid, whiteBalance } from "./capture/sheet.js";
import { checkQuality } from "./capture/quality.js";
import { segmentGrid } from "./segmentation/grid.js";
import { measure } from "./measurement/geometry.js";
import { colorClasses } from "./color/rules.js";
import { morphologyRules } from "./morphology/rules.js";
import { renderReview } from "./review/screen.js";
import { particlesCsv, summaryCsv } from "./export/csv.js";

/** Run one photo through parts 1-5 and return particle rows (planned). */
export async function processPhoto(imageData, metadata) {
  throw new Error("Part 8: processPhoto is not implemented yet");
}
