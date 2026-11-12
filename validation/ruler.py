"""Find a ruler in a photo and read the scale from its millimetre ticks, with no help.

Used by lab_photo_check.py for the lab's "Rows A-H" photos, which have a steel
ruler on the background instead of the printed markers. Steps:

1. **Find the ticks.** Rotate the photo over a range of angles and slide a narrow
   strip across it; the ruler's tick edge is the strip whose brightness repeats most
   strongly along its length. A wide strip then fixes the angle (within 2.5 degrees
   of the coarse one), since it only stays periodic when it lines up with the ticks.
2. **Tell millimetres from inches.** Moving inward from a tick edge, a strip sees
   only the longer ticks, so the repeat grows. On a millimetre edge it goes 0.5 mm,
   1 mm, 5 mm, 10 mm (the 5 mm ticks and the printed numbers), so the 1 mm repeat has
   partners 5 and 10 times longer. On an inch edge every step is x2 (1/32, 1/16, 1/8 ...)
   and no x5 or x10 partner appears. A repeat seen on several strips with such a
   partner is 0.5 mm or 1 mm; if both P and 2P qualify, P is the 0.5 mm ticks
   (there are no 2 mm ticks). Of the rest, the one on the most strips wins.
   Inch-only rulers are not handled and can give a wrong value (EX_02_S03): check
   the result with lab_photo_check.py --ruler-check before trusting a new setup.
3. **Refine.** The repeat is measured again from the autocorrelation at lags of
   10-50 mm, which averages over hundreds of ticks.

Returns None when no millimetre edge is found; the caller then needs a scale by hand.
"""
import os

import cv2
import numpy as np


def _rotate(g, ang):
    h, w = g.shape
    M = cv2.getRotationMatrix2D((w / 2, h / 2), ang, 1.0)
    return cv2.warpAffine(g, M, (w, h), flags=cv2.INTER_LINEAR, borderValue=float(np.median(g))), M


def _strip_scores(g, sw=32, step=16, win=1024, wstep=256, pmin=5, pmax=45):
    """Periodicity score and period for every (window, strip) of a vertical strip grid."""
    h, w = g.shape
    win = min(win, h - 1)
    cs = np.cumsum(np.pad(g, ((0, 0), (1, 0))), axis=1)
    xs = np.arange(0, w - sw, step)
    prof = (cs[:, xs + sw] - cs[:, xs]) / sw
    ys = np.arange(0, h - win, wstep) if h - win > 0 else np.array([0])
    hann = np.hanning(win)[:, None]
    fr = np.fft.rfftfreq(win)
    band = (fr > 1 / pmax) & (fr < 1 / pmin)
    score = np.zeros((len(ys), len(xs)))
    per = np.zeros_like(score)
    for i, y in enumerate(ys):
        p = prof[y:y + win]
        p = p - cv2.blur(p, (1, 31))
        f = np.abs(np.fft.rfft(p * hann, axis=0))[band]
        score[i] = f.max(axis=0) / (np.median(f, axis=0) + 1e-9)
        per[i] = 1 / fr[band][f.argmax(axis=0)]
    return xs, ys, score, per


def _period(p, pmax):
    """Strongest repeat of a 1-D profile (px) and its strength over the median spectrum."""
    n = len(p)
    p = (p - p.mean()) * np.hanning(n)
    f = np.abs(np.fft.rfft(p))
    fr = np.fft.rfftfreq(n)
    band = (fr > 1 / pmax) & (fr < 1 / 5)
    k = int(np.argmax(np.where(band, f, 0)))
    if k == 0 or not band.any():
        return 0.0, 0.0
    a, b, c = f[k - 1], f[k], f[min(k + 1, len(f) - 1)]
    den = a - 2 * b + c
    kk = k + (float(np.clip(0.5 * (a - c) / den, -0.5, 0.5)) if den else 0.0)
    return n / kk, f[k] / (np.median(f[band]) + 1e-9)


def _refine(p, ppm):
    """px per mm from autocorrelation peaks at 10-50 mm."""
    p = p - p.mean()
    n = len(p)
    ac = np.correlate(p, p, "full")[n - 1:]
    est = []
    for mm in (10, 20, 30, 40, 50):
        lag = int(round(mm * ppm))
        w = max(3, int(0.3 * ppm))
        if lag + w + 1 >= n * 0.8:
            continue
        k = lag - w + int(np.argmax(ac[lag - w:lag + w]))
        a, b, c = ac[k - 1], ac[k], ac[k + 1]
        den = a - 2 * b + c
        est.append((k + (0.5 * (a - c) / den if den else 0)) / mm)
    return est


def find_ruler(img):
    """Scale and position of a millimetre ruler in a BGR photo, or None.

    Returns px_per_mm, its spread over lags and strips, the angle, the ruler's span
    across (in the rotated photo) and a mask of the ruler in photo coordinates.
    """
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32) if img.ndim == 3 else img.astype(np.float32)
    h, w = g.shape
    coarse = []
    for ang in np.arange(-8, 8.1, 2.0):
        r, _ = _rotate(g, ang)
        xs, ys, sc, _ = _strip_scores(r)
        i, j = np.unravel_index(sc.argmax(), sc.shape)
        coarse.append((sc[i, j], ang, int(xs[j])))
    del r
    _, a0, x0 = max(coarse)
    r0, _ = _rotate(g, a0)
    xa, xb = max(0, x0 - 400), min(w, x0 + 432)
    crop = r0[:, xa:xb].copy()
    del r0
    # fine angle: a wide strip only stays periodic when it lines up with the ticks
    fine = []
    for d in np.arange(-2.5, 2.6, 0.25):
        rc, _ = _rotate(crop, d)
        fine.append((_strip_scores(rc[:, 100:-100], sw=128, step=16)[2].max(), d))
    ang = a0 + max(fine)[1]
    r, M = _rotate(g, ang)
    # the ticks' extent along the ruler
    xs, ys, sc, _ = _strip_scores(r[:, x0:x0 + 64], sw=32, step=32)
    good = ys[sc[:, 0] > 0.3 * sc[:, 0].max()]
    y0, y1 = int(good.min()), int(min(h, good.max() + 1024))
    # repeats across the ruler's width
    strips = []
    for x in range(max(0, x0 - 1000), min(w - 8, x0 + 1000), 6):
        P, snr = _period(r[y0:y1, x:x + 8].mean(axis=1).astype(np.float64), pmax=min(900, (y1 - y0) / 3))
        if snr > 8 and P > 0:
            strips.append((x, P, snr))
    strong = [s for s in strips if s[2] > 15]
    # groups of strips with the same repeat (within 1%); a real tick zone spans several strips
    groups = []
    for st in sorted(strong, key=lambda t: t[1]):
        if groups and st[1] / groups[-1][-1][1] - 1 < 0.01:
            groups[-1].append(st)
        else:
            groups.append([st])
    cands = []
    for same in groups:
        P = float(np.median([t[1] for t in same]))
        partner = any(abs(t[1] / (m * P) - 1) < 0.04 for t in strips for m in (5, 10))
        if len(same) >= 4 and 5 <= P <= 120 and partner:
            cands.append((P, same))
    if os.environ.get("RULER_DEBUG"):
        for P, same in cands:
            print(f"   candidate {P:.2f} px: {len(same)} strips, strength {max(t[2] for t in same):.0f}")
    best = None
    for P, same in cands:
        # there are no 2 mm ticks: if P and 2P both qualify, P is the 0.5 mm ticks
        if any(abs(Q / (2 * P) - 1) < 0.02 for Q, _ in cands):
            continue
        key = (len(same), sum(t[2] for t in same))
        if best is None or key > best[0]:
            best = (key, P, same)
    if best is None:
        return None
    _, P1, same = best
    # the 0.5 mm ticks, if this edge has them, give more ticks per mm to refine on
    half = [s for s in strong if abs(s[1] / (P1 / 2) - 1) < 0.01]
    use = sorted(same + half, key=lambda s: -s[2])[:4]
    est = []
    for x, _, _ in use:
        est += _refine(r[y0:y1, x:x + 8].mean(axis=1).astype(np.float64), P1)
    if not est:
        return None
    ppm = float(np.median(est))
    # the ruler body: the unbroken run of ruler-like strips around the tick edge (gaps under
    # 4 mm, e.g. the printed numbers), plus a margin; particle columns farther out stay in
    ruler_x = sorted(t[0] for t in strips if any(abs(t[1] / (m * ppm) - 1) < 0.03 for m in (0.5, 1, 5, 10)))
    tx = use[0][0]
    lo = hi = tx
    for xx in sorted((x for x in ruler_x if x < tx), reverse=True):
        if lo - xx > 4 * ppm:
            break
        lo = xx
    for xx in (x for x in ruler_x if x > tx):
        if xx - hi > 4 * ppm:
            break
        hi = xx
    rx0, rx1 = lo - 3 * ppm, hi + 8 + 3 * ppm
    band = np.zeros((h, w), np.uint8)
    band[:, int(max(0, rx0)):int(min(w, rx1))] = 1
    mask = cv2.warpAffine(band, cv2.invertAffineTransform(M), (w, h), flags=cv2.INTER_NEAREST) > 0
    return {"px_per_mm": ppm, "spread": float(np.std(est)), "n_estimates": len(est), "angle_deg": float(ang),
            "tick_x": int(use[0][0]), "y_span": (y0, y1), "ruler_x_span": (float(rx0), float(rx1)),
            "has_half_mm": bool(half), "mask": mask}


def check_image(img, res, px_per_display_mm=6, height_px=600):
    """The ruler straightened and scaled to 6 px per measured mm, with a red line every 10 mm.

    If the scale is right, each printed number sits the same way against its line all
    the way down; if not, the numbers drift. This is how the lab photos were checked.
    """
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
    r, _ = _rotate(g.astype(np.float32), res["angle_deg"])
    ppm, tx = res["px_per_mm"], res["tick_x"]
    y0, y1 = res["y_span"]
    crop = r[y0:y1, max(0, int(tx - 30 * ppm)):int(tx + 30 * ppm)].astype(np.uint8)
    s = px_per_display_mm / ppm
    crop = cv2.cvtColor(cv2.resize(crop, None, fx=s, fy=s, interpolation=cv2.INTER_AREA), cv2.COLOR_GRAY2BGR)
    for y in range(0, crop.shape[0], 10 * px_per_display_mm):
        cv2.line(crop, (0, y), (crop.shape[1], y), (0, 0, 255), 1)
    return crop[:height_px]


if __name__ == "__main__":
    import argparse
    from pathlib import Path
    ap = argparse.ArgumentParser(description="Read the scale from a ruler in each photo.")
    ap.add_argument("photos", nargs="+")
    ap.add_argument("--check-image", help="write one image per photo to this folder, to check the scale by eye")
    a = ap.parse_args()
    for path in a.photos:
        img = cv2.imread(path)
        res = find_ruler(img)
        name = Path(path).name
        if res is None:
            print(f"{name}: no millimetre ruler found")
            continue
        print(f"{name}: {res['px_per_mm']:.3f} px/mm (spread {res['spread']:.3f}, {res['n_estimates']} estimates), "
              f"angle {res['angle_deg']:+.2f}, 0.5 mm ticks: {res['has_half_mm']}")
        if a.check_image:
            Path(a.check_image).mkdir(parents=True, exist_ok=True)
            cv2.imwrite(str(Path(a.check_image) / f"{Path(path).stem}_ruler.png"), check_image(img, res))
