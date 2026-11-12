// Part 3: browser port of pipeline/mippr/measurement/uncertainty.py. Planned; nothing here is implemented yet.
// Must give the same results as the Python reference (checked by the parity tests, see web/README.md).

/**
 * Length and width (px) with the edge drawn at 40% (outer) and 60% (inner) of the particle's contrast:
 * {lengthPxOuter, lengthPxInner, widthPxOuter, widthPxInner}. Needs only threshold, dilate and connected
 * components, which OpenCV.js has.
 */
export function sizeRange(mask, diff, fraction = 0.5, spread = 0.1) {
  throw new Error("Part 3: size uncertainty is not implemented yet");
}
