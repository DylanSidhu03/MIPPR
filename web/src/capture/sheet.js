// Part 1: browser port of pipeline/mippr/capture/sheet.py.
// The layout is plain geometry (no DOM, no OpenCV). Detection and rectification take the OpenCV.js
// module as their first argument (see ../opencv.js), so the same code runs in the browser and in Node.
// Parity with the Python reference is checked by web/tests/.

export const BACKGROUNDS = Object.freeze(["white_grid", "black_grid", "checkerboard"]);
export const PAPERS = Object.freeze({ letter: Object.freeze([215.9, 279.4]), a4: Object.freeze([210.0, 297.0]) });
export const ARUCO_DICT = "DICT_4X4_50";
export const LAYOUT_VERSION = 1;

const LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ";

const DEFAULTS = Object.freeze({
  background: "white_grid",
  paper: "letter",
  boxMm: 12.0, // "around 10 mm or more"; particles in scope are 0.5-5 mm
  lineMm: 0.5, // "Standard" design, chosen November 5, 2026
  marginMm: 8.0, // unprinted edge most printers need
  markerMm: 18.0,
  gapMm: 8.0, // between the markers' inner edge and the grid, room for labels
  boxLabels: true, // also print each box's label (e.g. B4) small in its top-left corner
  labelZoneMm: Object.freeze([6.5, 3.2]), // top-left corner kept for the label
});

/** Python's float floor division (`a // b`), which can differ from Math.floor(a / b) near whole numbers. */
function floorDiv(a, b) {
  let mod = a % b;
  let div = (a - mod) / b;
  if (mod && (b < 0) !== (mod < 0)) {
    mod += b;
    div -= 1;
  }
  if (!div) return 0;
  const f = Math.floor(div);
  return div - f > 0.5 ? f + 1 : f;
}

/** Python's round(x, ndigits) for the values used here: half to even. */
export function pyRound(x, ndigits = 0) {
  const k = 10 ** ndigits;
  const v = x * k;
  const r = Math.round(v);
  return (Math.abs(v % 1) === 0.5 && r % 2 ? r - 1 : r) / k;
}

/** Geometry of one printable sheet, in mm from the top-left of the paper. */
export class Layout {
  constructor(options = {}) {
    const o = { ...DEFAULTS, ...options };
    if (!BACKGROUNDS.includes(o.background)) throw new Error(`background must be one of ${BACKGROUNDS.join(", ")}`);
    if (!(o.paper in PAPERS)) throw new Error(`paper must be one of ${Object.keys(PAPERS).join(", ")}`);
    for (const k of Object.keys(DEFAULTS)) this[k] = o[k];
    this.labelZoneMm = Object.freeze([...o.labelZoneMm]);
    Object.freeze(this);
  }

  get sizeMm() {
    return PAPERS[this.paper];
  }

  get cols() {
    const w = this.sizeMm[0] - 2 * (this.marginMm + this.markerMm + this.gapMm);
    return floorDiv(w, this.boxMm);
  }

  get rows() {
    const h = this.sizeMm[1] - 2 * (this.marginMm + this.markerMm + this.gapMm);
    return Math.min(floorDiv(h, this.boxMm), 26);
  }

  /** Top-left corner of the grid, centred on the sheet. */
  get gridOriginMm() {
    const [w, h] = this.sizeMm;
    return [(w - this.cols * this.boxMm) / 2, (h - this.rows * this.boxMm) / 2];
  }

  get gridSizeMm() {
    return [this.cols * this.boxMm, this.rows * this.boxMm];
  }

  /** IDs for the top-left, top-right, bottom-right and bottom-left markers. */
  markerIds() {
    const papers = Object.keys(PAPERS);
    const base = 4 * (BACKGROUNDS.indexOf(this.background) * papers.length + papers.indexOf(this.paper));
    return [base, base + 1, base + 2, base + 3];
  }

  /** {marker id: 4 corners [x, y] (TL, TR, BR, BL as OpenCV reports them)} in sheet mm. */
  markerCornersMm() {
    const [w, h] = this.sizeMm;
    const m = this.marginMm;
    const s = this.markerMm;
    const origins = [[m, m], [w - m - s, m], [w - m - s, h - m - s], [m, h - m - s]];
    const out = {};
    this.markerIds().forEach((id, i) => {
      const [x, y] = origins[i];
      out[id] = [[x, y], [x + s, y], [x + s, y + s], [x, y + s]];
    });
    return out;
  }

  boxLabel(row, col) {
    return `${LETTERS[row]}${col + 1}`;
  }

  /** End points of the printed 100 mm check line, in the bottom margin. */
  scaleLineMm() {
    const [w, h] = this.sizeMm;
    const y = h - this.marginMm - this.markerMm / 2;
    return [[w / 2 - 50, y], [w / 2 + 50, y]];
  }

  /** {name: [x, y, w, h, grey level 0-255]} white-balance patches in the top margin. */
  patchesMm() {
    const w = this.sizeMm[0];
    const y = this.marginMm + 2;
    return { white: [w / 2 - 26, y, 24, 12, 255], grey: [w / 2 + 2, y, 24, 12, 128] };
  }

  equals(other) {
    return other instanceof Layout && Object.keys(DEFAULTS).every((k) =>
      Array.isArray(this[k]) ? this[k].every((v, i) => v === other[k][i]) : this[k] === other[k]);
  }
}

/** The Layout whose corner markers these IDs belong to (default box and line sizes). */
export function layoutFromMarkerIds(ids) {
  const wanted = new Set(Array.from(ids, Number));
  for (const background of BACKGROUNDS) {
    for (const paper of Object.keys(PAPERS)) {
      const lay = new Layout({ background, paper });
      if (lay.markerIds().some((i) => wanted.has(i))) return lay;
    }
  }
  throw new Error("No MIPPR sheet markers found in the photo.");
}

// ── Finding the sheet in a photo ───────────────────────────────────────────

function toGray(cv, img) {
  if (img.channels() === 1) return img.clone();
  const gray = new cv.Mat();
  cv.cvtColor(img, gray, img.channels() === 4 ? cv.COLOR_RGBA2GRAY : cv.COLOR_BGR2GRAY);
  return gray;
}

/**
 * ArUco 4x4_50 markers -> {id: 4 corners [x, y] in photo px}.
 * A 4-channel image is taken as RGBA (canvas ImageData via cv.matFromImageData), 3 channels as BGR like Python.
 */
export function detectMarkers(cv, img) {
  const gray = toGray(cv, img);
  const dict = cv.getPredefinedDictionary(cv[ARUCO_DICT]);
  const params = new cv.aruco_DetectorParameters();
  const refine = new cv.aruco_RefineParameters(10, 3, true);
  const det = new cv.aruco_ArucoDetector(dict, params, refine);
  const corners = new cv.MatVector();
  const ids = new cv.Mat();
  const rejected = new cv.MatVector();
  try {
    det.detectMarkers(gray, corners, ids, rejected);
    const out = {};
    const idList = ids.data32S; // N x 1 in OpenCV 4.x, 1 x N in 5.x
    for (let k = 0; k < idList.length; k++) {
      const c = corners.get(k);
      const p = c.data32F;
      out[idList[k]] = [[p[0], p[1]], [p[2], p[3]], [p[4], p[5]], [p[6], p[7]]];
      c.delete();
    }
    return out;
  } finally {
    [gray, dict, params, refine, det, corners, ids, rejected].forEach((m) => m.delete());
  }
}

/**
 * Locate a printed MIPPR sheet from its corner markers: layout, px per mm and the photo -> sheet homography.
 * Mirrors the marker stage of find_sheet in sheet.py; the grid-crossing refinement is not ported yet.
 * Throws an Error with a readable reason.
 */
export function findSheet(cv, img, { pxPerMm = null, layout = null } = {}) {
  let found = detectMarkers(cv, img);
  layout ??= layoutFromMarkerIds(Object.keys(found));
  const expected = layout.markerCornersMm();
  found = Object.fromEntries(Object.entries(found).filter(([k]) => k in expected));
  const keys = Object.keys(found).map(Number).sort((a, b) => a - b);
  if (keys.length < 2) {
    throw new Error(`Found ${keys.length} of the 4 corner markers; at least 2 are needed. ` +
      "Is the whole sheet in the photo?");
  }
  if (pxPerMm == null) {
    // Keep about the photo's own resolution.
    const sides = Object.values(found).map((c) => Math.hypot(c[1][0] - c[0][0], c[1][1] - c[0][1]));
    pxPerMm = pyRound(sides.reduce((a, b) => a + b, 0) / sides.length / layout.markerMm, 1);
  }
  const src = keys.flatMap((k) => found[k].flat());
  const dst = keys.flatMap((k) => expected[k].flat().map((v) => v * pxPerMm));
  const srcMat = cv.matFromArray(src.length / 2, 1, cv.CV_64FC2, src);
  const dstMat = cv.matFromArray(dst.length / 2, 1, cv.CV_64FC2, dst);
  const H = cv.findHomography(srcMat, dstMat);
  const homography = Array.from(H.data64F);
  [srcMat, dstMat, H].forEach((m) => m.delete());
  if (homography.length !== 9) throw new Error("Could not fit the sheet's perspective from the markers.");
  return { layout, pxPerMm, homography, markers: found, markersFound: keys.length };
}

/** Sheet size in px at the sheet's px per mm. */
export function sheetSizePx(sheet) {
  return sheet.layout.sizeMm.map((v) => pyRound(v * sheet.pxPerMm));
}

/** The whole sheet flattened with the marker homography (for margins: patches, scale line). Caller deletes it. */
export function rectifySheet(cv, sheet, img, interpolation = cv.INTER_LINEAR) {
  const [w, h] = sheetSizePx(sheet);
  const H = cv.matFromArray(3, 3, cv.CV_64F, sheet.homography);
  const out = new cv.Mat();
  cv.warpPerspective(img, out, H, new cv.Size(w, h), interpolation, cv.BORDER_REPLICATE, new cv.Scalar());
  H.delete();
  return out;
}

/** The flattened grid image (box by box, from the refined grid crossings). */
export function rectifyGrid(sheet, img) {
  throw new Error("Part 1: rectifyGrid (grid-crossing refinement) is not implemented yet");
}

/** Per-channel gains from the printed white patch; grey patch check. */
export function whiteBalance(sheet, img) {
  throw new Error("Part 1: whiteBalance is not implemented yet");
}
