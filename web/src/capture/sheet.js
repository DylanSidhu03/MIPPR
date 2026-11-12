// Part 1: browser port of pipeline/mippr/capture/sheet.py. Planned; nothing here is implemented yet.
// Must give the same results as the Python reference (checked by the parity tests, see web/README.md).

/**
 * ArUco 4x4_50 corner markers -> {ids, corners}. Check the OpenCV.js build includes ArUco, or use a JS marker library.
 */
export function detectMarkers(imageData) {
  throw new Error("Part 1: detectMarkers is not implemented yet");
}

/**
 * Layout from marker IDs, px per mm, homography, refined with the grid's line crossings -> Sheet
 */
export function findSheet(imageData) {
  throw new Error("Part 1: findSheet is not implemented yet");
}

/**
 * The flattened grid image
 */
export function rectifyGrid(sheet, imageData) {
  throw new Error("Part 1: rectifyGrid is not implemented yet");
}

/**
 * Per-channel gains from the printed white patch; grey patch check
 */
export function whiteBalance(sheet, imageData) {
  throw new Error("Part 1: whiteBalance is not implemented yet");
}
