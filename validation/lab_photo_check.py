"""Compare the app's measurements with the lab's hand measurements on one of the lab's layout photos.

The lab's "Rows A-H" photos (Drive folder "microplastics photo") show hand-picked
particles laid out in 8 columns on a white background, one column per plate row,
with a steel ruler for scale. Their hand measurements are in the ParticleCount
spreadsheets (Drive), one row per well (W05-W96). See docs/LAB_DATA.md.

This script:
1. reads the scale from the ruler on its own (ruler.py: finds the millimetre edge
   and refines over hundreds of ticks), or from `--ruler` / `--px-per-mm`,
2. finds the particles: dark ones on a white background or light ones on a black
   background (threshold, half-maximum edge), leaving out the ruler,
3. measures them with the pipeline's own measure() and v2 rules,
4. groups them into one column per plate row in the sheet (A-H, or fewer), tries
   each column order and reading direction, and keeps the one whose lengths agree
   best with the sheet. Within a column, particles are aligned with the wells by
   length, top to bottom, so extra specks and missing particles are skipped.
   Particles away from the plate's grid (on tape or card edges) are left out.
5. reports agreement for length, width, colour and shape.

It is a validation tool, not part of the app: the photos have no printed markers.

    python validation/lab_photo_check.py PHOTO.jpg SHEET.xlsx|SHEET.csv SAMPLE_ID \
        [--ruler X0 X1 Y0 Y1] [--roi X0 X1 Y0 Y1] [--px-per-mm N] [--out FILE.json]

`--ruler` is a strip along the ruler's tick edge, in the coordinates of the photo
scaled to 1200 px wide; without it the ruler is found automatically. `--roi` (same
coordinates) limits detection to where the particles are laid out, for photos with
other marks on the background. `validation/run_lab_photos.py` runs a list of photos.
"""
import argparse
import json
import re
import statistics
import sys
from collections import Counter
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from mippr.color.rules import lab_cie  # noqa: E402
from mippr.export import morphology  # noqa: E402
from mippr.measurement.geometry import measure  # noqa: E402
from mippr.segmentation.edges import fill_holes, refine_edges  # noqa: E402
from ruler import find_ruler  # noqa: E402

PREVIEW_W = 1200
MAX_LENGTH_MM = 40  # the lab's longest non-fiber particle is 35 mm


def ruler_scale(gray, x0, x1, y0, y1):
    """px per mm from the ruler ticks. The strongest repeat is taken as the 0.5 mm ticks."""
    s = gray.shape[1] / PREVIEW_W
    est = []
    for dx in (0, 4, 8):
        prof = gray[int(y0 * s):int(y1 * s), int((x0 + dx) * s):int((x0 + dx + 12) * s)].mean(axis=1)
        prof = prof - prof.mean()
        n = len(prof)
        f = np.abs(np.fft.rfft(prof * np.hanning(n)))
        fr = np.fft.rfftfreq(n)
        k = int(np.argmax(np.where((fr > 1 / 120) & (fr < 1 / 5), f, 0)))
        a, b, c = f[k - 1], f[k], f[k + 1]
        ppm0 = n / (k + 0.5 * (a - c) / (a - 2 * b + c)) / 0.5
        ac = np.correlate(prof, prof, "full")[n - 1:]
        for mm in (10, 20, 30):
            lag = int(mm * ppm0)
            w = max(3, int(0.3 * ppm0))
            if lag + w + 1 >= n:
                continue
            k2 = lag - w + int(np.argmax(ac[lag - w:lag + w]))
            a, b, c = ac[k2 - 1], ac[k2], ac[k2 + 1]
            est.append((k2 + 0.5 * (a - c) / (a - 2 * b + c)) / mm)
    return float(np.median(est)), float(np.std(est))


def find_particles(img, px_per_mm, exclude=None, high=60, low=25, min_size_mm=0.25, roi=None):
    """Labels of dark particles on a white background, or light ones on a black background.

    The background is whichever is larger, the white or the black area. Outlines
    are drawn at half the particle's contrast with a smoothed background. A colour
    distance (ΔE) was tried and drew outlines too wide on white, from the coloured
    fringes around particles. `exclude` is a mask of pixels to leave out (the ruler).
    """
    h, w = img.shape[:2]
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    comps = []
    for kind, m in (("white", g > 170), ("black", g < 80)):
        n, lab, st, _ = cv2.connectedComponentsWithStats(m.astype(np.uint8), connectivity=8)
        if n > 1:
            k = 1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA]))
            comps.append((st[k, cv2.CC_STAT_AREA], kind, (lab == k).astype(np.uint8)))
    _, background, region = max(comps, key=lambda c: c[0])
    cnts, _ = cv2.findContours(region, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    region = np.zeros_like(region)
    cv2.fillPoly(region, [cv2.convexHull(max(cnts, key=len))], 1)
    region = cv2.erode(region, np.ones((41, 41), np.uint8))
    if exclude is not None:
        region[exclude] = 0
    if roi is not None:
        s = w / PREVIEW_W
        keep = np.zeros_like(region)
        keep[int(roi[2] * s):int(roi[3] * s), int(roi[0] * s):int(roi[1] * s)] = 1
        region &= keep
    bg = cv2.resize(cv2.medianBlur(cv2.resize(img, None, fx=0.1, fy=0.1, interpolation=cv2.INTER_AREA), 15), (w, h))
    gb = cv2.cvtColor(bg, cv2.COLOR_BGR2GRAY).astype(np.float64)
    sign = 1 if background == "white" else -1
    diff = np.clip(sign * (gb - g), 0, 255) * region
    hi = diff > high
    min_area = int((min_size_mm * px_per_mm) ** 2)

    def relabel(mask):
        n, lab, st, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=8)
        good = np.zeros(n, bool)
        good[np.unique(lab[hi])] = True
        good[0] = False
        good &= st[:, cv2.CC_STAT_AREA] >= min_area
        lut = np.zeros(n, np.int32)
        lut[good] = np.arange(1, good.sum() + 1)
        return lut[lab]

    labels = relabel(diff > low)
    labels = relabel(refine_edges(fill_holes(labels > 0), diff, 0.5))
    return labels, diff, bg, background


COLOR_KEYS = ("L_mean", "a_mean", "b_mean", "L_sd", "H_mean", "S_mean", "V_mean", "opacity",
              "color_secondary", "color_secondary_fraction", "color_confidence")


def lab_sample(img, mask, n=300, seed=0):
    """Up to n CIE Lab pixels from inside the particle (eroded by 1 px), for fitting the colour rules."""
    inner = cv2.erode(mask.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)
    px = img[inner if inner.sum() >= 4 else mask]
    if len(px) > n:
        px = px[np.random.default_rng(seed).choice(len(px), n, replace=False)]
    return [[round(v, 1) for v in row] for row in lab_cie(px).tolist()]


def read_sheet(path, sample):
    """{well: row} for one sample from a ParticleCount spreadsheet, .xlsx or .csv (W-numbered wells only)."""
    norm = lambda h: re.sub(r"[^a-z0-9]", "", str(h).lower()) if h is not None else ""  # noqa: E731
    keys = {"sampleid": "sample", "particleid": "pid", "particleshape": "shape", "particlecolor": "color",
            "particlelength": "L", "particlelengthum": "L", "particlewidth": "W", "particlewidthum": "W"}
    out = {}
    if str(path).lower().endswith(".csv"):
        import csv
        with open(path, newline="") as fh:
            tables = [[tuple(r) for r in csv.reader(fh)]]
    else:
        import openpyxl
        tables = [list(ws.iter_rows(values_only=True))
                  for ws in openpyxl.load_workbook(path, read_only=True, data_only=True).worksheets]
    for table in tables:
        rows = [r for r in table if any(c not in (None, "") for c in r)]
        if not rows or "sampleid" not in [norm(h) for h in rows[0]]:
            continue
        idx = {keys[norm(h)]: i for i, h in enumerate(rows[0]) if norm(h) in keys}
        for r in rows[1:]:
            d = {k: (r[i] if i < len(r) else None) for k, i in idx.items()}
            pid = str(d.get("pid") or "").strip()
            if str(d.get("sample") or "").strip() == sample and re.fullmatch(r"W\d+", pid):
                out[f"W{int(pid[1:]):02d}"] = d
    return out


def main_cluster(particles, k=3.0):
    """Indices of the particles laid out on the plate grid: the largest group of points linked
    at under k times the median nearest-neighbour distance. Specks on tape or card edges
    around the disc are farther away and fall out."""
    xy = np.array([[p["x"], p["y"]] for p in particles])
    if len(xy) < 3:
        return np.arange(len(xy))
    d = np.hypot(*(xy[:, None, :] - xy[None, :, :]).transpose(2, 0, 1))
    np.fill_diagonal(d, np.inf)
    link = d < k * np.median(d.min(axis=1))
    group = -np.ones(len(xy), int)
    for i in range(len(xy)):
        if group[i] >= 0:
            continue
        group[i], stack = i, [i]
        while stack:
            j = stack.pop()
            for n in np.nonzero(link[j] & (group < 0))[0]:
                group[n] = i
                stack.append(n)
    biggest = np.bincount(group).argmax()
    return np.nonzero(group == biggest)[0]


def columns(particles, keep, ncol, iters=30):
    """Column index (0 = leftmost) for each kept particle: 1-D k-means on x, started from the widest gaps."""
    xs = np.array([particles[i]["x"] for i in keep])
    order = np.argsort(xs)
    col = np.zeros(len(keep), int)
    if ncol > 1:
        for c in np.sort(np.argsort(np.diff(xs[order]))[-(ncol - 1):]):
            col[order[c + 1:]] += 1
    for _ in range(iters):
        centres = np.array([xs[col == c].mean() if (col == c).any() else np.nan for c in range(ncol)])
        centres = np.sort(centres[~np.isnan(centres)])
        if len(centres) < ncol:
            break
        new = np.abs(xs[:, None] - centres[None, :]).argmin(axis=1)
        if (new == col).all():
            break
        col = new
    return col


def align(app, hand, gap=0.6):
    """Best order-preserving pairing of two length lists (top to bottom), allowing skips on both sides.

    Score per pair: 1 - |log(app/hand)|, so similar lengths pair up; skipping costs `gap`.
    Extra specks and missing particles become skips instead of breaking the column.
    """
    n, m = len(app), len(hand)
    S = np.zeros((n + 1, m + 1))
    S[:, 0] = -gap * np.arange(n + 1)
    S[0, :] = -gap * np.arange(m + 1)
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            pair = 1 - abs(np.log(app[i - 1] / hand[j - 1])) if app[i - 1] > 0 and hand[j - 1] > 0 else -1
            S[i, j] = max(S[i - 1, j - 1] + pair, S[i - 1, j] - gap, S[i, j - 1] - gap)
    pairs, i, j = [], n, m
    while i > 0 and j > 0:
        pair = 1 - abs(np.log(app[i - 1] / hand[j - 1])) if app[i - 1] > 0 and hand[j - 1] > 0 else -1
        if np.isclose(S[i, j], S[i - 1, j - 1] + pair):
            if pair > 0:
                pairs.append((i - 1, j - 1))
            i, j = i - 1, j - 1
        elif np.isclose(S[i, j], S[i - 1, j] - gap):
            i -= 1
        else:
            j -= 1
    return pairs[::-1], float(S[n, m])


def match(particles, sheet):
    """Assign wells: one column per plate row in the sheet (A-H, or fewer), particles in a column
    aligned top to bottom with its wells by length (skips allowed for specks and missing
    particles). Tries each column order and reading direction and keeps the best total score.
    """
    row_of = lambda w: (int(w[1:]) - 1) // 12  # noqa: E731
    letters = sorted({row_of(w) for w in sheet})
    ncol = len(letters)
    keep = main_cluster(particles)
    col = np.full(len(particles), -1)
    col[keep] = columns(particles, keep, ncol)
    measured = [w for w in sheet if sheet[w].get("L") not in (None, "")]
    best = None
    for rtl in (True, False):
        for top_down in (True, False):
            m, total = {}, 0.0
            for c in range(ncol):
                idx = sorted((i for i in range(len(particles)) if col[i] == c),
                             key=lambda i: particles[i]["y"], reverse=not top_down)
                letter = letters[ncol - 1 - c] if rtl else letters[c]
                wells = sorted(w for w in measured if row_of(w) == letter)
                pairs, score = align([particles[i]["length_mm"] for i in idx],
                                     [float(sheet[w]["L"]) / 1000 for w in wells])
                m.update({idx[a]: wells[b] for a, b in pairs})
                total += score
            if len(m) >= 5 and (best is None or total > best[0]):
                pairs = [(particles[i]["length_mm"], float(sheet[w]["L"]) / 1000) for i, w in m.items()]
                best = (total, float(np.corrcoef(*zip(*pairs))[0, 1]), m, rtl, top_down)
    per_col = [int((col == c).sum()) for c in range(ncol)] + [int((col < 0).sum())]
    return (best[1:] if best else None), per_col


def detect(img, a):
    """Scale, background type and every particle found on the photo (with colour pixels)."""
    s = img.shape[1] / PREVIEW_W
    exclude = None
    if a.px_per_mm:
        ppm, sd, how = a.px_per_mm, 0.0, "given"
    elif a.ruler:
        ppm, sd = ruler_scale(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float64), *a.ruler)
        how = "ruler strip given"
    else:
        found = find_ruler(img)
        if found is None:
            print("no millimetre ruler found; give --px-per-mm or --ruler")
            sys.exit(2)
        ppm, sd, exclude, how = found["px_per_mm"], found["spread"], found["mask"], "ruler found automatically"
    if a.ruler:
        exclude = np.zeros(img.shape[:2], bool)
        exclude[:, int((a.ruler[0] - 15) * s):] = True
    print(f"scale: {ppm:.3f} px/mm (spread {sd:.3f}, {how}), {1000 / ppm:.1f} um/px")
    labels, diff, bg, background = find_particles(img, ppm, exclude, roi=a.roi)
    print(f"background: {background}")
    measured = measure(labels, img, 1000 / ppm, diff, 0.5, 3, bg_img=bg)
    particles = []
    for m in measured:
        if m["feret_max_um"] > MAX_LENGTH_MM * 1000:
            continue  # the ruler's end, a label or the disc's edge, not a particle
        particles.append({"x": m["x_um"] / 1000, "y": m["y_um"] / 1000, "length_mm": m["feret_max_um"] / 1000,
                          "width_mm": m["feret_min_um"] / 1000, "color": m["color_label"],
                          "morphology": morphology(m)[0], "color_stats": {k: m.get(k) for k in COLOR_KEYS},
                          "lab_px": lab_sample(img, labels == m["particle"])})
    return ppm, sd, how, background, particles


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("photo")
    ap.add_argument("sheet")
    ap.add_argument("sample")
    ap.add_argument("--ruler", nargs=4, type=float, metavar=("X0", "X1", "Y0", "Y1"))
    ap.add_argument("--roi", nargs=4, type=float, metavar=("X0", "X1", "Y0", "Y1"))
    ap.add_argument("--px-per-mm", type=float)
    ap.add_argument("--out")
    ap.add_argument("--cache", help="save the detected particles here, or read them if the file exists")
    a = ap.parse_args()
    cache = Path(a.cache) if a.cache else None
    if cache and cache.exists():
        c = json.loads(cache.read_text())
        ppm, sd, how, background, particles = c["px_per_mm"], c["spread"], c["how"], c["background"], c["particles"]
        print(f"scale: {ppm:.3f} px/mm ({how}; detection read from {cache.name})")
    else:
        img = cv2.imread(a.photo)
        ppm, sd, how, background, particles = detect(img, a)
        if cache:
            cache.write_text(json.dumps({"px_per_mm": ppm, "spread": sd, "how": how, "background": background,
                                         "particles": particles}))
    sheet = read_sheet(a.sheet, a.sample)
    print(f"particles found: {len(particles)}; sheet rows with a W well: {len(sheet)}")
    best, per_col = match(particles, sheet)
    print("particles per column, left to right:", per_col[:-1], f"(+{per_col[-1]} strays left out)")
    summary = {"photo": Path(a.photo).name, "sample": a.sample, "px_per_mm": ppm, "scale_spread": sd,
               "scale_source": how, "background": background, "n_found": len(particles), "n_sheet": len(sheet),
               "per_column": per_col}
    if best is None:
        print("no column could be matched (particle counts differ from the sheet)")
        if a.out:
            Path(a.out).write_text(json.dumps({**summary, "matched": 0, "rows": []}, indent=1))
        return
    r, m, rtl, top_down = best
    print(f"layout: columns {'right to left' if rtl else 'left to right'} are rows A-H, wells "
          f"{'top to bottom' if top_down else 'bottom to top'}; {len(m)} matched; length correlation r = {r:.3f}")
    rows = []
    for i, w in sorted(m.items(), key=lambda kv: kv[1]):
        h, p = sheet[w], particles[i]
        if h.get("L") in (None, "") or h.get("W") in (None, ""):
            continue
        rows.append({"well": w, "hand_length_mm": float(h["L"]) / 1000, "app_length_mm": p["length_mm"],
                     "hand_width_mm": float(h["W"]) / 1000, "app_width_mm": p["width_mm"],
                     "hand_shape": str(h.get("shape") or ""), "app_morphology": p["morphology"],
                     "hand_color": str(h.get("color") or ""), "app_color": p["color"],
                     "color_stats": p["color_stats"], "lab_px": p["lab_px"]})
    for what in ("length", "width"):
        hand = np.array([x[f"hand_{what}_mm"] for x in rows])
        app = np.array([x[f"app_{what}_mm"] for x in rows])
        pct = 100 * (app - hand) / hand
        k, c = np.polyfit(hand, app, 1)
        print(f"{what}: median {statistics.median(pct):+.1f}% (middle 80%: {np.percentile(pct, 10):+.1f} to "
              f"{np.percentile(pct, 90):+.1f}%), within 10%: {int((abs(pct) <= 10).sum())}/{len(pct)}, "
              f"fit app = {k:.3f} x hand {c * 1000:+.0f} um")
    print("colour (hand, app):", Counter((x["hand_color"], x["app_color"]) for x in rows).most_common(5))
    print("shape (hand, app):", Counter((x["hand_shape"], x["app_morphology"]) for x in rows).most_common(5))
    if a.out:
        Path(a.out).write_text(json.dumps({**summary, "matched": len(m), "correlation": r, "layout_rtl": rtl,
                                           "layout_top_down": top_down, "rows": rows}))


if __name__ == "__main__":
    main()
