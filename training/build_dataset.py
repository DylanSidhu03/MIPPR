"""Part 10: build the training dataset: crops, labels, shape values and a split by sample.

    python training/build_dataset.py --runs RUN_DIR [RUN_DIR ...] [--labels advisor_labels.csv ...] \\
        [--gold gold.txt] [--keep-splits OLD_DATASET/manifest.json] --out DATASET_DIR

Inputs:
- `--runs`: output folders of the pipeline (`mippr.cli grid` / `batch`, the browser app's download,
  or validation/sheet_check.py's OUT_DIR). Every particles.csv inside (any depth) with a `crop_file`
  column is read; the crops are found next to it. A particle found twice (a batch's combined file
  and its per-photo file) is kept once, preferring the reviewed copy.
- Labels come from two places:
  - reviewed rows: `review_status` confirmed or corrected; the label is `morphology_label` (which
    holds the corrected value), the labeller `reviewed_by` / `reviewer_role`.
  - `--labels`: box-label sheets like validation/templates/advisor_labels.csv (photo, sheet, box,
    morphology, ..., labeller), joined to the run rows by photo (`photo_file`, its stem, or
    `picture_label`) and box (the `particle_id` without its -1, -2 blob number). Their role is
    `--labels-role` (expert by default).
- `--gold`: the fixed gold test set, one `particle_ref` (or `sample_id:<id>` for a whole sample)
  per line. Gold particles get split `gold` and are never trained on; the other particles of a gold
  sample get split `excluded`, so the gold set stays unseen conditions too.
- `--keep-splits`: a previous dataset's manifest.json. Samples seen before keep their split, so a
  test sample never moves into training at a later retraining. New samples are assigned by a
  hash of the sample ID.

Rules:
- Rejected rows are left out (the replaced originals of a split or merge are marked rejected; the
  new rows they became are used, if they have a crop).
- Rows without a crop, without a usable label, or whose label is "other" are left out, and counted.
- If two expert labels disagree, the particle is left out (`conflict`). An expert label wins over
  a community one; a box-label sheet wins over a review of the same role.
- Splits are by sample (`sample_id`), never by photo or particle: train / val / test.

Writes DATASET_DIR/manifest.csv (one row per particle), manifest.json (counts, splits by sample,
what was left out and why, and the manifest's hash, which the model records), and crops/ (copies,
so the folder can be zipped and trained on elsewhere, e.g. Colab).
"""
import argparse
import hashlib
import json
import shutil
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from common import (FEATURES, NOT_TRAINED_ON, normalise_label, read_csv, sha256_file, write_csv,  # noqa: E402
                    write_json)

SPLITS = ("train", "val", "test")
DEFAULT_FRACTIONS = (0.7, 0.15, 0.15)
ROLE_WEIGHT = {"expert": 1.0, "community": 0.5}  # community labels vary more (training/README.md)
REVIEWED = ("confirmed", "corrected")
MANIFEST_COLUMNS = (["crop", "label", "split", "sample_id", "particle_ref", "image_id", "photo_file", "particle_id",
                     "background_type", "source", "labeller", "labeller_role", "weight", "rule_label",
                     "morphology_source", "outline_edited", "derived_from", "crop_sha1", "run_file"]
                    + [name for name, _ in FEATURES])


def _base_box(particle_id):
    return str(particle_id or "").split("-")[0].upper()


def find_particle_files(run_dirs):
    """Every pipeline particles.csv (has crop_file and particle_ref) under the run folders."""
    out = []
    for d in run_dirs:
        d = Path(d)
        files = [d] if d.is_file() else sorted(d.rglob("particles.csv"))
        for f in files:
            with open(f, encoding="utf-8-sig") as fh:
                header = fh.readline()
            if "crop_file" in header and "particle_ref" in header:
                out.append(f)
    return out


def _crop_path(csv_path, crop_file):
    if not crop_file:
        return None
    p = csv_path.parent / crop_file
    if p.exists():
        return p
    alt = csv_path.parent / "crops" / Path(crop_file).name  # e.g. crops.zip unpacked next to the CSV
    return alt if alt.exists() else None


def _rank(row):
    """Which copy of a particle to keep: a reviewed one first, then one whose crop was found."""
    return (row.get("review_status", "auto") not in ("", "auto"), row["_crop"] is not None)


def read_runs(run_dirs):
    """{(image_id, particle_ref): row} with `_crop` (absolute path or None) and `_run_file`."""
    rows = {}
    for f in find_particle_files(run_dirs):
        for r in read_csv(f):
            r["_crop"] = _crop_path(f, r.get("crop_file", ""))
            r["_run_file"] = str(f)
            key = (r.get("image_id", ""), r["particle_ref"])
            if key not in rows or _rank(r) > _rank(rows[key]):
                rows[key] = r
    return rows


def read_box_labels(paths, role):
    """Rows of box-label sheets (validation/templates/advisor_labels.csv), names matched loosely."""
    keys = {"photo": ("photo", "photofile", "photofilename", "filename", "file", "image"), "box": ("box", "boxlabel"),
            "sheet": ("sheet", "background", "backgroundtype", "sheettype"),
            "morphology": ("morphology", "shape", "particleshape", "morphologylabel"),
            "labeller": ("labeller", "labeler", "labelledby", "labeledby"), "role": ("role", "labellerrole")}
    alias = {a: k for k, names in keys.items() for a in names}
    out = []
    for path in paths:
        for raw in read_csv(path):
            r = {}
            for k, v in raw.items():
                kk = alias.get("".join(c for c in str(k).lower() if c.isalnum()))
                if kk and not r.get(kk):
                    r[kk] = (v or "").strip()
            if r.get("photo") and r.get("box") and not r["photo"].upper().startswith("EXAMPLE"):
                out.append({"photo": r["photo"], "box": r["box"].upper(), "sheet": r.get("sheet", ""),
                            "label_raw": r.get("morphology", ""), "labeller": r.get("labeller", ""),
                            "role": (r.get("role") or role).lower(), "file": str(path)})
    return out


def _photo_keys(row):
    pf = row.get("photo_file", "")
    return {k for k in (pf, Path(pf).stem, row.get("picture_label", "")) if k}


def collect_labels(rows, box_labels, skipped):
    """{key: [candidate labels]} from reviewed rows and box-label sheets."""
    cands = defaultdict(list)
    for key, r in rows.items():
        if r.get("review_status") in REVIEWED and r.get("morphology_label"):
            cands[key].append({"raw": r["morphology_label"], "source": "review", "labeller": r.get("reviewed_by", ""),
                               "role": (r.get("reviewer_role") or "community").lower()})
    by_photo_box = defaultdict(list)
    for key, r in rows.items():
        if r.get("review_status") != "rejected":
            for pk in _photo_keys(r):
                by_photo_box[(pk, _base_box(r.get("particle_id")))].append(key)
    for b in box_labels:
        keys = by_photo_box.get((b["photo"], b["box"])) or by_photo_box.get((Path(b["photo"]).stem, b["box"]), [])
        keys = sorted(set(keys))
        if not keys:
            skipped["label_not_matched"] += 1
            continue
        if len(keys) > 1:  # several kept blobs in the box: which one the label means is unclear
            skipped["label_box_has_several_particles"] += 1
            continue
        cands[keys[0]].append({"raw": b["label_raw"], "source": f"labels:{Path(b['file']).name}",
                               "labeller": b["labeller"], "role": b["role"], "sheet": b["sheet"]})
    return cands


def choose_label(cands):
    """(candidate, None) or (None, reason): expert over community, sheet over review, conflicts out."""
    norm = []
    for c in cands:
        lab = normalise_label(c["raw"])
        if lab:
            norm.append({**c, "label": lab})
    if not norm:
        return None, "label_unknown"
    experts = [c for c in norm if c["role"] == "expert"]
    pool = experts or norm
    if len({c["label"] for c in pool}) > 1:
        return None, "conflict"
    pool.sort(key=lambda c: c["source"] == "review")  # a box-label sheet first
    return pool[0], None


def _hash_unit(text, seed):
    return int(hashlib.sha256(f"{seed}:{text}".encode()).hexdigest()[:12], 16) / 16 ** 12


def assign_splits(samples, fractions=DEFAULT_FRACTIONS, seed=0, keep=None):
    """{sample_id: split}. Samples in `keep` keep their split; the others are ordered by a hash of
    their ID and cut by the fractions, giving val and test at least one sample when there are 3+."""
    keep = keep or {}
    out = {s: keep[s] for s in samples if s in keep and keep[s] in SPLITS}
    new = sorted((s for s in samples if s not in out), key=lambda s: _hash_unit(s, seed))
    n = len(new)
    n_val, n_test = round(fractions[1] * n), round(fractions[2] * n)
    if n >= 3:
        n_val, n_test = max(1, n_val), max(1, n_test)
    for i, s in enumerate(new):
        out[s] = "test" if i < n_test else "val" if i < n_test + n_val else "train"
    return out


def read_gold(path):
    """(particle_refs, sample_ids) from a gold list: one particle_ref or sample_id:<id> per line."""
    refs, samples = set(), set()
    if path:
        for line in Path(path).read_text().splitlines():
            line = line.split("#")[0].strip()
            if line.startswith("sample_id:"):
                samples.add(line[len("sample_id:"):].strip())
            elif line and line != "particle_ref":
                refs.add(line)
    return refs, samples


def build(run_dirs, out_dir, label_files=(), gold=None, keep_splits=None, fractions=DEFAULT_FRACTIONS, seed=0,
          labels_role="expert", copy_crops=True, exclude_labels=NOT_TRAINED_ON):
    """Write the dataset (manifest.csv, manifest.json, crops/) and return its manifest.json contents."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    skipped = Counter()
    rows = read_runs(run_dirs)
    cands = collect_labels(rows, read_box_labels(label_files, labels_role), skipped)
    gold_refs, gold_samples = read_gold(gold)
    picked = []
    for key in sorted(cands):
        r = rows[key]
        if r.get("review_status") == "rejected":
            skipped["rejected"] += 1
            continue
        c, why = choose_label(cands[key])
        if why:
            skipped[why] += 1
            continue
        if c["label"] in exclude_labels:
            skipped[f"label_{c['label']}"] += 1
            continue
        if r["_crop"] is None:
            skipped["no_crop"] += 1  # e.g. rows made by a split or merge, which have no crop yet
            continue
        if c.get("sheet") and r.get("background_type") and c["sheet"] != r["background_type"] \
                and c["sheet"] in ("white_grid", "black_grid", "checkerboard"):
            skipped["sheet_mismatch_noted"] += 1  # kept; the markers' background type is used
        picked.append((r, c))
    listed_gold_samples = set(gold_samples)
    gold_samples |= {r.get("sample_id", "") for r, _ in picked if r["particle_ref"] in gold_refs}
    keep = {}
    if keep_splits:
        keep = json.loads(Path(keep_splits).read_text()).get("sample_splits", {})
    pool_samples = sorted({r.get("sample_id", "") for r, _ in picked} - gold_samples)
    splits = assign_splits(pool_samples, fractions, seed, keep)
    if copy_crops:
        (out_dir / "crops").mkdir(exist_ok=True)
    manifest, warnings = [], []
    for i, (r, c) in enumerate(picked):
        if r["particle_ref"] in gold_refs or r.get("sample_id") in listed_gold_samples:
            split = "gold"
            if c["role"] != "expert":
                warnings.append(f"gold particle {r['particle_ref']} has a {c['role']} label")
        elif r.get("sample_id") in gold_samples:
            split = "excluded"
        else:
            split = splits[r.get("sample_id", "")]
        src = Path(r["_crop"])
        if copy_crops:
            rel = f"crops/{i:05d}_{r['particle_ref']}.png"
            shutil.copyfile(src, out_dir / rel)
        else:
            rel = str(src.resolve())
        m = {"crop": rel, "label": c["label"], "split": split, "sample_id": r.get("sample_id", ""),
             "particle_ref": r["particle_ref"], "image_id": r.get("image_id", ""),
             "photo_file": r.get("photo_file", ""), "particle_id": r.get("particle_id", ""),
             "background_type": r.get("background_type", ""), "source": c["source"], "labeller": c["labeller"],
             "labeller_role": c["role"], "weight": ROLE_WEIGHT.get(c["role"], 0.5),
             "rule_label": r.get("morphology_label_original") or r.get("morphology_label", ""),
             "morphology_source": r.get("morphology_source", ""), "outline_edited": r.get("outline_edited", ""),
             "derived_from": r.get("derived_from", ""),
             "crop_sha1": hashlib.sha1(src.read_bytes()).hexdigest(), "run_file": r["_run_file"]}
        m.update({name: r.get(name, "") for name, _ in FEATURES})
        manifest.append(m)
    gold_in = {m["particle_ref"] for m in manifest if m["split"] == "gold"}
    for ref in sorted(gold_refs - gold_in):
        warnings.append(f"gold particle {ref} not found among the labelled particles")
    write_csv(out_dir / "manifest.csv", manifest, MANIFEST_COLUMNS)
    counts = defaultdict(Counter)
    for m in manifest:
        counts[m["split"]][m["label"]] += 1
    info = {
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "manifest_sha256": sha256_file(out_dir / "manifest.csv"),
        "n_particles": len(manifest),
        "counts": {s: dict(sorted(c.items())) for s, c in sorted(counts.items())},
        "sample_splits": {**{s: v for s, v in sorted(splits.items())}, **{s: "gold" for s in sorted(gold_samples)}},
        "fractions": list(fractions), "seed": seed,
        "skipped": dict(sorted(skipped.items())),
        "warnings": warnings,
        "runs": [str(p) for p in run_dirs], "label_files": [str(p) for p in label_files],
        "gold_file": str(gold) if gold else None,
        "features": [name for name, _ in FEATURES],
    }
    write_json(out_dir / "manifest.json", info)
    return info


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--runs", nargs="+", required=True, help="pipeline output folders (particles.csv + crops/)")
    ap.add_argument("--labels", nargs="*", default=[], help="box-label sheets (validation/templates/advisor_labels.csv)")
    ap.add_argument("--labels-role", default="expert", choices=["expert", "community"])
    ap.add_argument("--gold", help="gold list: one particle_ref or sample_id:<id> per line")
    ap.add_argument("--keep-splits", help="a previous dataset's manifest.json, so samples keep their split")
    ap.add_argument("--fractions", nargs=3, type=float, default=list(DEFAULT_FRACTIONS), metavar=("TRAIN", "VAL", "TEST"))
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--no-copy", action="store_true", help="point at the crops where they are instead of copying")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    info = build(a.runs, a.out, a.labels, a.gold, a.keep_splits, tuple(a.fractions), a.seed, a.labels_role,
                 not a.no_copy)
    print(f"{info['n_particles']} particles -> {a.out}")
    for split, c in info["counts"].items():
        print(f"  {split}: " + ", ".join(f"{k} {v}" for k, v in c.items()))
    if info["skipped"]:
        print("  left out: " + ", ".join(f"{k} {v}" for k, v in info["skipped"].items()))
    for w in info["warnings"]:
        print(f"  warning: {w}")


if __name__ == "__main__":
    main()
