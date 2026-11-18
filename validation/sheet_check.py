"""Compare the app with known answers on photos of labelled particles on the printed sheets.

The lab re-photographs particles it has already labelled, one per box, and writes down
which particle went into which box (`templates/well_to_box.csv`). For every box this
compares the app's size, colour and morphology with the lab's (and with calipers, where
measured), counts missed and extra detections, and shows which flag values go with wrong
sizes, which is how the flag thresholds are set (docs/PIPELINE.md, part 7).

    python validation/sheet_check.py --photos PHOTO_DIR --boxes well_to_box.csv \\
        --lab EX_01_ParticleCount.xlsx [more sheets ...] [--calipers calipers.csv] \\
        [--tolerance 0.10] --out OUT_DIR

    python validation/sheet_check.py --photos PHOTO_DIR --boxes advisor_labels.csv --out OUT_DIR

Inputs:
- `--boxes`: one row per particle placed: photo, box, sample_id, particle_id (the lab's
  ID, e.g. W05 or F03). Boxes not listed are expected to be empty. Or a box-label sheet
  (`templates/advisor_labels.csv`) with the morphology and colour in each row, which needs
  no `--lab`; its optional hand-measured length_mm/width_mm are the size reference.
  Column names and class names are matched loosely (Colour/color, Fibre/Fiber/fiber ...).
- `--lab`: the lab's ParticleCount spreadsheets (.xlsx or .csv) with those particles.
- `--calipers` (optional): sample_id, particle_id, length_mm, width_mm. Where given,
  calipers are the size reference instead of the spreadsheet.
- `--line-mm` (optional): measured length of the sheets' printed 100 mm line.

Writes OUT_DIR/particles.csv (one row per box: the lab's answer next to the app's),
OUT_DIR/report.md (the agreement tables) and each photo's normal outputs in
OUT_DIR/photos/. Outlines are not labelled by hand: where a size or label is wrong,
look at that particle in its photo's overlay.png to see why.
"""
import argparse
import csv
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "pipeline"))
sys.path.insert(0, str(HERE))

from mippr.cli import run_grid  # noqa: E402
from mippr.export import FLAGS  # noqa: E402

from lab_sheets import lab_color, lab_shape, normalise_id, read_lab_records  # noqa: E402

THRESHOLDS = (0.03, 0.05, 0.075, 0.10, 0.15, 0.20, 0.30)  # size_uncertainty values tried
SIZE_FLAGS = [f for f in FLAGS if f not in ("flag_low_confidence", "flag_bundle", "flag_scale")]


# Column names accepted in the --boxes file, matched ignoring case, spaces and punctuation
# ("Photo file name", "photo_file", "Colour", "color" ...).
_BOX_KEYS = {
    "photo": ("photo", "photofile", "photofilename", "filename", "file", "image"),
    "box": ("box", "boxlabel"),
    "sample_id": ("sampleid", "sample"),
    "particle_id": ("particleid",),
    "sheet": ("sheet", "background", "backgroundtype", "sheettype"),
    "morphology": ("morphology", "shape", "particleshape", "morphologylabel"),
    "color": ("colour", "color", "particlecolour", "particlecolor", "colourlabel", "colorlabel"),
    "color_secondary": ("secondcolour", "secondcolor", "colour2", "color2", "secondarycolour", "secondarycolor",
                        "coloursecondary", "colorsecondary"),
    "tar_like": ("tarlike", "tar"),
    "length_mm": ("lengthmm", "length"),
    "width_mm": ("widthmm", "width"),
    "labeller": ("labeller", "labeler", "labelledby", "labeledby"),
    "note": ("note", "notes", "comment", "comments"),
}
_ALIAS = {a: k for k, names in _BOX_KEYS.items() for a in names}


def _key(h):
    return _ALIAS.get("".join(c for c in str(h).lower() if c.isalnum()))


def _yes(v):
    return str(v or "").strip().lower() in ("yes", "y", "true", "1", "x")


def _sheet(v):
    s = "_".join(str(v or "").lower().replace("-", " ").replace("_", " ").split())
    return {"white": "white_grid", "black": "black_grid", "checker": "checkerboard"}.get(s, s)


def read_boxes(path):
    """One row per particle placed. Two layouts, mixed freely:

    - well-to-box (templates/well_to_box.csv): photo, box, sample_id, particle_id; the labels come
      from the lab's spreadsheets (--lab).
    - box labels (templates/advisor_labels.csv): photo, sheet, box, morphology, colour, second_colour,
      tar_like, length_mm, width_mm, labeller, notes; the labels are in the row itself (`truth`), and
      hand-measured length/width (`hand`) are the size reference like calipers.
    """
    rows = []
    with open(path, newline="", encoding="utf-8-sig") as fh:
        for raw in csv.DictReader(fh):
            r = {}
            for k, v in raw.items():
                if k and _key(k) and not r.get(_key(k)):
                    r[_key(k)] = (v or "").strip()
            if not (r.get("photo") and r.get("box")):
                continue
            box = r["box"].upper()
            row = {"photo": r["photo"], "box": box, "sample_id": r.get("sample_id", "") or Path(r["photo"]).stem,
                   "particle_id": normalise_id(r.get("particle_id", "")) or box, "note": r.get("note", ""),
                   "sheet": _sheet(r.get("sheet")), "labeller": r.get("labeller", "")}
            if r.get("morphology") or r.get("color"):
                L, W = _f(r.get("length_mm")), _f(r.get("width_mm"))
                row["truth"] = {"shape": r.get("morphology", ""), "color": r.get("color", ""),
                                "shape_class": lab_shape(r.get("morphology")), "color_class": lab_color(r.get("color")),
                                "color_secondary": lab_color(r.get("color_secondary")) or "",
                                "tar_like": _yes(r.get("tar_like")), "length_mm": None, "width_mm": None}
                if L or W:
                    row["hand"] = {"length_mm": L, "width_mm": W}
            rows.append(row)
    return rows


def read_calipers(path):
    out = {}
    if not path:
        return out
    with open(path, newline="") as fh:
        for r in csv.DictReader(fh):
            key = (r["sample_id"].strip(), normalise_id(r["particle_id"]))
            out[key] = {k: float(r[k]) if r.get(k) not in (None, "") else None for k in ("length_mm", "width_mm")}
    return out


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _true(v):
    return v is True or str(v) == "True"


def run_photos(photo_dir, photos, out_dir, line_mm=None):
    """{photo: (rows, error)} from the normal grid pipeline."""
    res = {}
    for n, photo in enumerate(sorted(photos), 1):
        try:
            rows = run_grid(Path(photo_dir) / photo, Path(out_dir) / "photos" / Path(photo).stem,
                            sample_id=Path(photo).stem, photo=n, line_mm=line_mm)
            res[photo] = (rows, "")
        except ValueError as e:
            res[photo] = ([], str(e).splitlines()[0])
    return res


def compare(boxes, results, lab, calipers):
    """One record per expected box and per extra detection."""
    out = []
    expected = defaultdict(dict)
    for b in boxes:
        expected[b["photo"]][b["box"]] = b
    for photo, (rows, error) in results.items():
        by_box = defaultdict(list)
        for r in rows:
            by_box[r["particle_id"].split("-")[0]].append(r)
        for box, b in sorted(expected[photo].items()):
            rec = {"photo": photo, "box": box, "sample_id": b["sample_id"], "particle_id": b["particle_id"],
                   "photo_error": error}
            truth = b.get("truth") or lab.get((b["sample_id"], b["particle_id"]))
            cal = b.get("hand") or calipers.get((b["sample_id"], b["particle_id"]), {})
            rec.update({"lab_found": truth is not None, "sheet": b.get("sheet", ""), "labeller": b.get("labeller", ""),
                        "note": b.get("note", ""), "lab_color_secondary": (truth or {}).get("color_secondary", ""),
                        "lab_tar_like": (truth or {}).get("tar_like", ""),
                        "lab_shape": truth["shape"] if truth else "", "lab_shape_class": (truth or {}).get("shape_class"),
                        "lab_color": truth["color"] if truth else "", "lab_color_class": (truth or {}).get("color_class"),
                        "lab_length_mm": (truth or {}).get("length_mm"), "lab_width_mm": (truth or {}).get("width_mm"),
                        "caliper_length_mm": cal.get("length_mm"), "caliper_width_mm": cal.get("width_mm")})
            found = by_box.get(box, [])
            rec["status"] = "missed" if not found else ("matched" if len(found) == 1 else "multi_blob")
            if found:
                r = max(found, key=lambda x: _f(x["area_mm2"]) or 0)  # several blobs: compare the largest
                fiber = r["morphology_label"] == "fiber" and _f(r["fiber_length_mm"])
                rec.update({"background_type": r["background_type"], "particle_ref": r["particle_ref"],
                            "app_length_mm": _f(r["fiber_length_mm"]) if fiber else _f(r["length_mm"]),
                            "app_width_mm": _f(r["width_mm"]), "size_length_source": r["size_length_source"],
                            "size_uncertainty": _f(r["size_uncertainty"]),
                            "app_color": r["color_label"], "app_morphology": r["morphology_label"],
                            "app_color_secondary": r.get("color_secondary", ""),
                            "review_reason": r["review_reason"], **{f: _true(r[f]) for f in SIZE_FLAGS}})
            # the size reference: calipers where measured, else the lab's spreadsheet
            ref = "calipers" if rec["caliper_length_mm"] else ("lab" if rec["lab_length_mm"] else "")
            rec["size_reference"] = ref
            ref_len = rec["caliper_length_mm"] or rec["lab_length_mm"]
            ref_wid = rec["caliper_width_mm"] or rec["lab_width_mm"]
            for what, ref_v in (("length", ref_len), ("width", ref_wid)):
                app_v = rec.get(f"app_{what}_mm")
                rec[f"{what}_error"] = (app_v - ref_v) / ref_v if app_v and ref_v else None
            if rec["lab_length_mm"] and rec["caliper_length_mm"]:
                rec["lab_vs_caliper_length"] = (rec["lab_length_mm"] - rec["caliper_length_mm"]) / rec["caliper_length_mm"]
            rec["color_correct"] = (rec["app_color"] == rec["lab_color_class"]) if found and rec["lab_color_class"] else None
            rec["morphology_correct"] = ((rec["app_morphology"] == rec["lab_shape_class"])
                                         if found and rec["lab_shape_class"] else None)
            out.append(rec)
        for box, found in sorted(by_box.items()):
            if box not in expected[photo]:
                r = found[0]
                out.append({"photo": photo, "box": box, "status": "extra", "particle_ref": r["particle_ref"],
                            "background_type": r["background_type"], "app_length_mm": _f(r["length_mm"]),
                            "app_color": r["color_label"], "app_morphology": r["morphology_label"]})
    return out


def _pct(xs):
    xs = sorted(xs)
    if not xs:
        return "–"
    q = lambda p: xs[min(len(xs) - 1, int(p * (len(xs) - 1) + 0.5))]  # noqa: E731
    return f"{100 * statistics.median(xs):+.1f}% (middle 80%: {100 * q(0.1):+.1f} to {100 * q(0.9):+.1f}%)"


def _confusion(recs, truth_key, app_key, correct_key):
    lines = ["| Lab class | Particles | App agrees | Most common app answers |", "|---|---|---|---|"]
    by = defaultdict(list)
    for r in recs:
        if r.get(correct_key) is not None:
            by[r[truth_key]].append(r)
    for cls, rs in sorted(by.items(), key=lambda kv: -len(kv[1])):
        ok = sum(r[correct_key] for r in rs)
        common = ", ".join(f"{a} {n}" for a, n in Counter(r[app_key] for r in rs).most_common(3))
        lines.append(f"| {cls} | {len(rs)} | {ok} ({100 * ok / len(rs):.0f}%) | {common} |")
    return lines


def threshold_table(recs, tolerance):
    """For each size_uncertainty threshold: flagged, wrong sizes caught and missed, false alarms."""
    rs = [r for r in recs if r.get("length_error") is not None and r.get("size_uncertainty") is not None]
    wrong = [abs(r["length_error"]) > tolerance for r in rs]
    lines = ["| Flag above | Flagged | Wrong sizes caught | Wrong sizes missed | Flagged but right |", "|---|---|---|---|---|"]
    best = None
    for t in THRESHOLDS:
        flag = [r["size_uncertainty"] > t for r in rs]
        tp = sum(f and w for f, w in zip(flag, wrong))
        fn = sum((not f) and w for f, w in zip(flag, wrong))
        fp = sum(f and not w for f, w in zip(flag, wrong))
        f1 = 2 * tp / (2 * tp + fn + fp) if tp else 0.0
        if best is None or f1 > best[0]:
            best = (f1, t)
        lines.append(f"| {t:.3f} | {sum(flag)} | {tp} | {fn} | {fp} |")
    return lines, (best[1] if best and best[0] > 0 else None), sum(wrong), len(rs)


def report(recs, tolerance, results):
    exp = [r for r in recs if r["status"] != "extra"]
    found = [r for r in exp if r["status"] in ("matched", "multi_blob")]
    L = ["# Sheet check: the app against the lab's labelled particles", ""]
    failed = {p: e for p, (_, e) in results.items() if e}
    L += [f"{len(results)} photos, {len(exp)} particles placed. Size reference: calipers where measured "
          f"({sum(r.get('size_reference') == 'calipers' for r in exp)}), otherwise the lab's spreadsheet. "
          f"A size counts as wrong when it is more than {100 * tolerance:.0f}% off.", ""]
    if failed:
        L += ["**Photos the app refused:**", ""] + [f"- {p}: {e}" for p, e in failed.items()] + [""]
    L += ["## Detection", "", "| Background | Found | Two or more blobs in the box | Extra detections in empty boxes |",
          "|---|---|---|---|"]
    for bg in sorted({r.get("background_type") or "" for r in recs} - {""}):
        L.append(f"| {bg} | {sum(r.get('background_type') == bg for r in found)} | "
                 f"{sum(r.get('background_type') == bg and r['status'] == 'multi_blob' for r in exp)} | "
                 f"{sum(r['status'] == 'extra' and r.get('background_type') == bg for r in recs)} |")
    L += ["", f"Placed {len(exp)}, found {len(found)}, missed {sum(r['status'] == 'missed' for r in exp)}, "
              f"extra detections {sum(r['status'] == 'extra' for r in recs)}.", ""]
    L += ["## Size", ""]
    for what in ("length", "width"):
        errs = [r[f"{what}_error"] for r in found if r.get(f"{what}_error") is not None]
        within = sum(abs(e) <= tolerance for e in errs)
        L.append(f"- **{what.capitalize()}**, app vs reference: {_pct(errs)}; within {100 * tolerance:.0f}%: "
                 f"{within} of {len(errs)}")
    lc = [r["lab_vs_caliper_length"] for r in exp if r.get("lab_vs_caliper_length") is not None]
    if lc:
        L.append(f"- **The lab's spreadsheet vs calipers** (length): {_pct(lc)} on {len(lc)} particles")
    L += ["", "| Group | Particles | Length error | Within tolerance |", "|---|---|---|---|"]
    groups = defaultdict(list)
    for r in found:
        if r.get("length_error") is not None:
            groups[f"background: {r['background_type']}"].append(r["length_error"])
            groups[f"lab shape: {r['lab_shape_class'] or r['lab_shape'] or '?'}"].append(r["length_error"])
    for g, errs in sorted(groups.items()):
        L.append(f"| {g} | {len(errs)} | {_pct(errs)} | {sum(abs(e) <= tolerance for e in errs)} |")
    L += ["", "## Colour", ""] + _confusion(found, "lab_color_class", "app_color", "color_correct")
    L += ["", "## Morphology", "", "Rubbery fragment and foam come from the v3 model; until then the rules call them fragment.", ""]
    L += _confusion(found, "lab_shape_class", "app_morphology", "morphology_correct")
    L += ["", "## Which flags catch wrong sizes", ""]
    rs = [r for r in found if r.get("length_error") is not None]
    wrong = [abs(r["length_error"]) > tolerance for r in rs]
    L += [f"{sum(wrong)} of {len(rs)} sizes are wrong (more than {100 * tolerance:.0f}% off).", "",
          "| Flag | Flagged | Wrong sizes it catches | Flagged but right |", "|---|---|---|---|"]
    for f in SIZE_FLAGS:
        flagged = [r.get(f) is True for r in rs]
        L.append(f"| `{f}` | {sum(flagged)} | {sum(a and w for a, w in zip(flagged, wrong))} | "
                 f"{sum(a and not w for a, w in zip(flagged, wrong))} |")
    for name, sub in (("all particles", found), ("fibers (by the lab's label)", [r for r in found if r.get("lab_shape_class") == "fiber"]),
                      ("everything else", [r for r in found if r.get("lab_shape_class") != "fiber"])):
        table, best, n_wrong, n = threshold_table(sub, tolerance)
        if not n:
            continue
        L += ["", f"### `size_uncertainty` thresholds, {name} ({n_wrong} wrong of {n})", ""] + table
        if best is not None:
            L.append(f"\nBest balance of caught and false alarms here: flag above **{best:.3f}** "
                     f"(the app uses 0.10 until this is decided).")
    L += ["", "Look at each wrong particle in `photos/<photo>/overlay.png` to see why (outline, label or the reference)."]
    return "\n".join(L) + "\n"


FIELDS = ["photo", "box", "sample_id", "particle_id", "status", "photo_error", "sheet", "background_type", "particle_ref",
          "lab_shape", "lab_shape_class", "app_morphology", "morphology_correct",
          "lab_color", "lab_color_class", "app_color", "color_correct", "lab_color_secondary", "app_color_secondary",
          "lab_tar_like",
          "size_reference", "lab_length_mm", "caliper_length_mm", "app_length_mm", "length_error", "size_length_source",
          "lab_width_mm", "caliper_width_mm", "app_width_mm", "width_error", "lab_vs_caliper_length",
          "size_uncertainty", *SIZE_FLAGS, "review_reason", "lab_found", "labeller", "note"]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--photos", required=True)
    ap.add_argument("--boxes", required=True)
    ap.add_argument("--lab", nargs="+", default=[], help="not needed when the --boxes file has the labels")
    ap.add_argument("--calipers")
    ap.add_argument("--tolerance", type=float, default=0.10, help="a size more than this far off counts as wrong")
    ap.add_argument("--line-mm", type=float)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    boxes = read_boxes(a.boxes)
    lab = read_lab_records(a.lab) if a.lab else {}
    calipers = read_calipers(a.calipers)
    if not a.lab and not any("truth" in b for b in boxes):
        ap.error("--boxes has no morphology/colour columns, so --lab spreadsheets are needed")
    missing = [(b["sample_id"], b["particle_id"]) for b in boxes
               if "truth" not in b and (b["sample_id"], b["particle_id"]) not in lab]
    if missing:
        print(f"warning: {len(missing)} placed particles aren't in the lab sheets, e.g. {missing[:3]}", file=sys.stderr)
    out = Path(a.out)
    results = run_photos(a.photos, {b["photo"] for b in boxes}, out, a.line_mm)
    recs = compare(boxes, results, lab, calipers)
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "particles.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(recs)
    (out / "report.md").write_text(report(recs, a.tolerance, results))
    print(f"{len(recs)} rows -> {out / 'particles.csv'}, {out / 'report.md'}")
    return recs


if __name__ == "__main__":
    main()
