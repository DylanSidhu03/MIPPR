// Part 2: browser port of pipeline/mippr/segmentation/grid.py. Planned; nothing here is implemented yet.
// Must give the same results as the Python reference (checked by the parity tests, see web/README.md).

/**
 * {labels, diff, band}: box-by-box difference, bridging across lines and label corners, hysteresis, half-maximum edges
 */
export function segmentGrid(rectified, layout, pxPerMm, params) {
  throw new Error("Part 2: segmentGrid is not implemented yet");
}

/**
 * [row, col] of the box containing a point
 */
export function boxOf(layout, pxPerMm, x, y) {
  throw new Error("Part 2: boxOf is not implemented yet");
}
