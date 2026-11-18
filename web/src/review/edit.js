// Geometry for the review screen's outline tools: split a particle along a drawn line, merge two particles,
// and turn a hand-drawn path into an outline. Masks are Uint8Array (0/1, width x height); outlines are
// polygons [[x, y], ...] in grid px with vertices at pixel centres, as corrections.js expects.

/** The 0/1 mask of one or more polygons (a particle's outline polygons), filled. */
export function polygonsMask(cv, polys, width, height) {
  const m = cv.Mat.zeros(height, width, cv.CV_8UC1);
  const vec = new cv.MatVector();
  const mats = polys.filter((p) => p.length >= 3).map((p) => cv.matFromArray(p.length, 1, cv.CV_32SC2, p.flat().map(Math.round)));
  for (const p of mats) vec.push_back(p);
  cv.fillPoly(m, vec, new cv.Scalar(1));
  const out = Uint8Array.from(m.data);
  [m, vec, ...mats].forEach((x) => x.delete());
  return out;
}

/** External contours of a 0/1 mask as polygons, largest first. */
export function contoursOf(cv, mask, width, height) {
  const m = new cv.Mat(height, width, cv.CV_8UC1);
  m.data.set(mask);
  const contours = new cv.MatVector();
  const hier = new cv.Mat();
  cv.findContours(m, contours, hier, cv.RETR_EXTERNAL, cv.CHAIN_APPROX_NONE);
  const polys = [];
  for (let i = 0; i < contours.size(); i++) {
    const c = contours.get(i);
    const pts = [];
    for (let j = 0; j < c.data32S.length; j += 2) pts.push([c.data32S[j], c.data32S[j + 1]]);
    polys.push(pts);
    c.delete();
  }
  [m, contours, hier].forEach((x) => x.delete());
  return polys.sort((a, b) => b.length - a.length);
}

/**
 * The pieces of `mask` after cutting it along the line p0 -> p1 (thickness `width` px, extended far past both
 * ends so a short stroke still cuts across). Returns one polygon per piece of at least `minPx` pixels,
 * largest first; fewer than two means the line didn't cut the particle in two.
 */
export function cutPieces(cv, mask, width, height, p0, p1, { thickness = 2, minPx = 4 } = {}) {
  const m = new cv.Mat(height, width, cv.CV_8UC1);
  m.data.set(mask);
  const dx = p1[0] - p0[0], dy = p1[1] - p0[1];
  const len = Math.hypot(dx, dy);
  if (len < 1) {
    m.delete();
    return [];
  }
  const far = 4 * (width + height);
  const a = new cv.Point(Math.round(p0[0] - (dx / len) * far), Math.round(p0[1] - (dy / len) * far));
  const b = new cv.Point(Math.round(p1[0] + (dx / len) * far), Math.round(p1[1] + (dy / len) * far));
  cv.line(m, a, b, new cv.Scalar(0), thickness, cv.LINE_8);
  const labels = new cv.Mat();
  const n = cv.connectedComponents(m, labels, 4, cv.CV_32S);
  const pieces = [];
  for (let k = 1; k < n; k++) {
    const piece = Uint8Array.from(labels.data32S, (v) => (v === k ? 1 : 0));
    if (piece.reduce((s, v) => s + v, 0) >= minPx) pieces.push(contoursOf(cv, piece, width, height)[0]);
  }
  [m, labels].forEach((x) => x.delete());
  return pieces.sort((p, q) => q.length - p.length);
}

/** The merged outline of two or more masks: the convex hull of their union (the reviewer can redraw it). */
export function mergedOutline(cv, masks, width, height) {
  const pts = [];
  for (const mask of masks) {
    for (let i = 0; i < mask.length; i++) if (mask[i]) pts.push(i % width, Math.floor(i / width));
  }
  const m = cv.matFromArray(pts.length / 2, 1, cv.CV_32SC2, pts);
  const hull = new cv.Mat();
  cv.convexHull(m, hull, false, true);
  const out = [];
  for (let j = 0; j < hull.data32S.length; j += 2) out.push([hull.data32S[j], hull.data32S[j + 1]]);
  [m, hull].forEach((x) => x.delete());
  return out;
}

/** A hand-drawn path as an outline: points closer than `minStep` px dropped; null if under 3 points. */
export function pathOutline(path, minStep = 1.5) {
  const out = [];
  for (const p of path) {
    const q = out[out.length - 1];
    if (!q || Math.hypot(p[0] - q[0], p[1] - q[1]) >= minStep) out.push([Math.round(p[0]), Math.round(p[1])]);
  }
  return out.length >= 3 ? out : null;
}
