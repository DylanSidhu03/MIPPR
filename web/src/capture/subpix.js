// Small JS versions of OpenCV functions: cornerSubPix and boxPoints, missing from the OpenCV.js 4.10.0 build,
// and warpPerspective computed as OpenCV 5 does it. They follow OpenCV's C++ (imgproc cornersubpix.cpp,
// samplers.cpp, warp_kernels.simd.hpp, core RotatedRect::points), float32 rounding included.

const f32 = Math.fround;

/**
 * cv::getRectSubPix for an 8-bit, 1-channel image into float32: a (w x h) patch centred on (cx, cy),
 * bilinearly sampled, edges replicated.
 */
function rectSubPix(src, width, height, w, h, cx, cy, dst) {
  const x0 = f32(cx - f32((w - 1) * 0.5));
  const y0 = f32(cy - f32((h - 1) * 0.5));
  const ix = Math.floor(x0);
  const iy = Math.floor(y0);
  if (ix >= 0 && ix + w < width && iy >= 0 && iy + h < height) {
    // OpenCV's 8u -> 32f fast path, rounding included.
    const a = Math.max(f32(x0 - ix), f32(0.0001));
    const b = f32(y0 - iy);
    const a12 = f32(a * f32(1 - b));
    const a22 = f32(a * b);
    const b1 = f32(1 - b);
    const s = (1 - a) / a;
    for (let i = 0; i < h; i++) {
      const row = (iy + i) * width + ix;
      let prev = f32(f32(1 - a) * f32(f32(b1 * src[row]) + f32(b * src[row + width])));
      for (let j = 0; j < w; j++) {
        const t = f32(f32(a12 * src[row + j + 1]) + f32(a22 * src[row + j + 1 + width]));
        dst[i * w + j] = f32(prev + t);
        prev = f32(t * s);
      }
    }
    return;
  }
  const a = f32(x0 - ix);
  const b = f32(y0 - iy);
  const w11 = f32(f32(1 - a) * f32(1 - b)), w12 = f32(a * f32(1 - b));
  const w21 = f32(f32(1 - a) * b), w22 = f32(a * b);
  const px = (x) => Math.min(Math.max(x, 0), width - 1);
  const py = (y) => Math.min(Math.max(y, 0), height - 1) * width;
  for (let i = 0; i < h; i++) {
    const r0 = py(iy + i), r1 = py(iy + i + 1);
    for (let j = 0; j < w; j++) {
      const c0 = px(ix + j), c1 = px(ix + j + 1);
      dst[i * w + j] = f32(f32(f32(f32(src[r0 + c0] * w11) + f32(src[r0 + c1] * w12)) +
        f32(src[r1 + c0] * w21)) + f32(src[r1 + c1] * w22));
    }
  }
}

/**
 * cv.cornerSubPix for an 8-bit greyscale Mat. `corners` is a list of [x, y]; returns the refined list
 * (float32 values, like OpenCV). `criteria` is {maxCount, epsilon}; leave either out to drop that test.
 */
export function cornerSubPix(cv, img, corners, [winW, winH], [zeroW, zeroH] = [-1, -1],
  { maxCount = null, epsilon = null } = {}) {
  if (img.type() !== cv.CV_8UC1) throw new Error("cornerSubPix: an 8-bit greyscale image is needed");
  const src = img.data;
  const width = img.cols, height = img.rows;
  const maxIters = maxCount == null ? 100 : Math.min(Math.max(maxCount, 1), 100);
  const eps2 = epsilon == null ? 0 : Math.max(epsilon, 0) ** 2;
  const ww = 2 * winW + 1, wh = 2 * winH + 1;
  const mask = new Float32Array(ww * wh);
  for (let i = 0; i < wh; i++) {
    const y = f32((i - winH) / winH);
    const vy = f32(Math.exp(f32(-y * y)));
    for (let j = 0; j < ww; j++) {
      const x = f32((j - winW) / winW);
      mask[i * ww + j] = f32(vy * f32(Math.exp(f32(-x * x))));
    }
  }
  if (zeroW >= 0 && zeroH >= 0 && zeroW * 2 + 1 < ww && zeroH * 2 + 1 < wh) {
    for (let i = winH - zeroH; i <= winH + zeroH; i++) {
      for (let j = winW - zeroW; j <= winW + zeroW; j++) mask[i * ww + j] = 0;
    }
  }
  const bw = ww + 2;
  const buf = new Float32Array(bw * (wh + 2));
  return corners.map(([x, y]) => {
    const tx = f32(x), ty = f32(y);
    let cx = tx, cy = ty;
    let iter = 0, err = 0;
    do {
      rectSubPix(src, width, height, bw, wh + 2, cx, cy, buf);
      let a = 0, b = 0, c = 0, bb1 = 0, bb2 = 0;
      for (let i = 0, k = 0; i < wh; i++) {
        const py = i - winH;
        const row = (i + 1) * bw + 1;
        for (let j = 0; j < ww; j++, k++) {
          const m = mask[k];
          const gx = f32(buf[row + j + 1] - buf[row + j - 1]);
          const gy = f32(buf[row + j + bw] - buf[row + j - bw]);
          const gxx = gx * gx * m, gxy = gx * gy * m, gyy = gy * gy * m;
          const px = j - winW;
          a += gxx;
          b += gxy;
          c += gyy;
          bb1 += gxx * px + gxy * py;
          bb2 += gxy * px + gyy * py;
        }
      }
      const det = a * c - b * b;
      if (Math.abs(det) <= Number.EPSILON * Number.EPSILON) break;
      const scale = 1 / det;
      const nx = f32(cx + c * scale * bb1 - b * scale * bb2);
      const ny = f32(cy - b * scale * bb1 + a * scale * bb2);
      const dx = f32(nx - cx), dy = f32(ny - cy);
      err = f32(f32(dx * dx) + f32(dy * dy));
      cx = nx;
      cy = ny;
      if (cx < 0 || cx >= width || cy < 0 || cy >= height) break;
    } while (++iter < maxIters && err > eps2);
    // Too far from the start means poor convergence: keep the start, as OpenCV does.
    if (Math.abs(cx - tx) > winW || Math.abs(cy - ty) > winH) return [tx, ty];
    return [cx, cy];
  });
}

/** cv.boxPoints: the 4 corners of a rotated rectangle [[cx, cy], [w, h], angle in degrees], in OpenCV's order. */
export function boxPoints([[cx, cy], [w, h], angle]) {
  const t = (angle * Math.PI) / 180;
  const b = f32(f32(Math.cos(t)) * 0.5);
  const a = f32(f32(Math.sin(t)) * 0.5);
  cx = f32(cx); cy = f32(cy); w = f32(w); h = f32(h);
  const p0 = [f32(f32(cx - f32(a * h)) - f32(b * w)), f32(f32(cy + f32(b * h)) - f32(a * w))];
  const p1 = [f32(f32(cx + f32(a * h)) - f32(b * w)), f32(f32(cy - f32(b * h)) - f32(a * w))];
  return [p0, p1, [f32(2 * cx - p0[0]), f32(2 * cy - p0[1])], [f32(2 * cx - p1[0]), f32(2 * cy - p1[1])]];
}

// ── warpPerspective as OpenCV 5 computes it ────────────────────────────────
// OpenCV 4.10 (the OpenCV.js build) rounds sample positions to 1/32 px; OpenCV 5 (the Python reference)
// interpolates in float32 (its SIMD path, used here for every pixel). The grid-crossing search is
// sensitive to single grey levels, so it uses this.

function inv3(m) {
  const det = m[0] * (m[4] * m[8] - m[5] * m[7]) - m[1] * (m[3] * m[8] - m[5] * m[6]) +
    m[2] * (m[3] * m[7] - m[4] * m[6]);
  if (det === 0) return [0, 0, 0, 0, 0, 0, 0, 0, 0];
  const d = 1 / det;
  return [
    (m[4] * m[8] - m[5] * m[7]) * d, (m[2] * m[7] - m[1] * m[8]) * d, (m[1] * m[5] - m[2] * m[4]) * d,
    (m[5] * m[6] - m[3] * m[8]) * d, (m[0] * m[8] - m[2] * m[6]) * d, (m[2] * m[3] - m[0] * m[5]) * d,
    (m[3] * m[7] - m[4] * m[6]) * d, (m[1] * m[6] - m[0] * m[7]) * d, (m[0] * m[4] - m[1] * m[3]) * d,
  ];
}

function roundEven(v) {
  const r = Math.round(v);
  return r - v === 0.5 && r % 2 ? r - 1 : r;
}

/** One output pixel: bilinear at (sx, sy) (float32), edges replicated, rounded half to even. */
function sample(src, sw, sh, cn, sx, sy, dst, o) {
  const ix = Math.floor(sx), iy = Math.floor(sy);
  const a = f32(sx - ix), b = f32(sy - iy);
  const x0 = Math.min(Math.max(ix, 0), sw - 1), x1 = Math.min(Math.max(ix + 1, 0), sw - 1);
  const y0 = Math.min(Math.max(iy, 0), sh - 1) * sw, y1 = Math.min(Math.max(iy + 1, 0), sh - 1) * sw;
  for (let k = 0; k < cn; k++) {
    const p00 = src[(y0 + x0) * cn + k], p01 = src[(y0 + x1) * cn + k];
    const p10 = src[(y1 + x0) * cn + k], p11 = src[(y1 + x1) * cn + k];
    const v0 = f32(a * (p01 - p00) + p00);
    const v1 = f32(a * (p11 - p10) + p10);
    const v = roundEven(f32(b * f32(v1 - v0) + v0));
    dst[o + k] = v < 0 ? 0 : v > 255 ? 255 : v;
  }
}

/** cv.warpPerspective(img, H, (w, h), INTER_LINEAR, BORDER_REPLICATE) for 8-bit images, as OpenCV 5 does it. */
export function warpPerspectiveLinear(cv, img, H, w, h) {
  const M = Float32Array.from(inv3(H));
  const cn = img.channels();
  const out = new cv.Mat(h, w, img.type());
  const src = img.data, dst = out.data;
  for (let y = 0; y < h; y++) {
    const mx = f32(f32(y * M[1]) + M[2]), my = f32(f32(y * M[4]) + M[5]), mw = f32(f32(y * M[7]) + M[8]);
    for (let x = 0; x < w; x++) {
      const sw = f32(M[6] * x + mw);
      sample(src, img.cols, img.rows, cn, f32(f32(M[0] * x + mx) / sw), f32(f32(M[3] * x + my) / sw),
        dst, (y * w + x) * cn);
    }
  }
  return out;
}
