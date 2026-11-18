// Particle crops: the JS twin of pipeline/mippr/crops.py. One small RGBA image per particle, cut from the
// white-balanced, flattened grid at full resolution: square, centred, padded, with alpha 0 outside the
// particle's outline (dilated by one pixel). Saved as crops/<particle_ref>.png (column crop_file).

export const PAD_FRAC = 0.15;
const PAD_MIN_PX = 4;

/** Python's round(): half to even. */
function roundHalfEven(x) {
  const r = Math.round(x);
  return r - x === 0.5 && r % 2 ? r - 1 : r;
}

/** [x0, y0, x1, y1]: a square window round the box, padded, clipped to an image of width w and height h. */
export function cropBox(x, y, bw, bh, w, h, padFrac = PAD_FRAC) {
  let side = Math.max(bw, bh);
  side += 2 * Math.max(PAD_MIN_PX, roundHalfEven(padFrac * side));
  const x0 = Math.floor((2 * x + bw - side) / 2), y0 = Math.floor((2 * y + bh - side) / 2);
  return [Math.max(0, x0), Math.max(0, y0), Math.min(w, x0 + side), Math.min(h, y0 + side)];
}

/**
 * {width, height, rgba} crop of particle `particle` (its label in the CV_32S `labels` Mat) from the CV_8UC3
 * BGR `img`, around the box {x, y, w, h}.
 */
export function cropParticle(img, labels, particle, box, padFrac = PAD_FRAC) {
  const W = img.cols, H = img.rows;
  const [x0, y0, x1, y1] = cropBox(box.x, box.y, box.w, box.h, W, H, padFrac);
  const w = x1 - x0, h = y1 - y0;
  const L = labels.data32S, src = img.data;
  const inside = new Uint8Array(w * h);
  for (let r = 0; r < h; r++) for (let c = 0; c < w; c++) inside[r * w + c] = L[(y0 + r) * W + x0 + c] === particle ? 1 : 0;
  const rgba = new Uint8ClampedArray(w * h * 4);
  for (let r = 0; r < h; r++) {
    for (let c = 0; c < w; c++) {
      let on = 0; // 3 x 3 dilation inside the window, as cv2.dilate on the cropped mask
      for (let dr = -1; dr <= 1 && !on; dr++) {
        for (let dc = -1; dc <= 1 && !on; dc++) {
          const rr = r + dr, cc = c + dc;
          if (rr >= 0 && rr < h && cc >= 0 && cc < w && inside[rr * w + cc]) on = 1;
        }
      }
      const s = 3 * ((y0 + r) * W + x0 + c), o = 4 * (r * w + c);
      rgba[o] = src[s + 2], rgba[o + 1] = src[s + 1], rgba[o + 2] = src[s], rgba[o + 3] = on ? 255 : 0;
    }
  }
  return { width: w, height: h, rgba };
}
