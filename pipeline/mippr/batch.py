"""Part 8, outputs: process a whole folder of sheet photos in one command.

Every photo in the folder goes through the same pipeline as `cli.py grid`. Writes:
- `photos/<photo>/`: each photo's own particles.csv, summary.csv, overlay.png, run.json
- `particles.csv`: every particle from every photo, one row each (docs/OUTPUT_CSV.md)
- `summary.csv`: one row per sample, across all its photos
- `batch_report.csv`: one row per photo: processed or refused, why, how many particles,
  how many flagged for review, and the photo quality problems
- `batch.json` and `NOTE.txt`

A photo that can't be processed (no printed sheet found, unreadable file) is listed in
the report with the reason, and the rest carry on.

The optional settings file is a CSV with one row per photo:
`photo, sample_id, photo_number, line_mm, date, operator, lab, setup, site`
(only `photo` is required). Without it, or for photos it doesn't list, the sample ID is
`--sample-id` if given, otherwise the photo's file name, and photos are numbered in
file-name order within each sample.
"""
import csv
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from . import __version__
from .export import COLUMNS, METADATA, NOTE, SUMMARY_COLUMNS, build_summary

PHOTO_TYPES = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".heic", ".webp"}
REPORT_COLUMNS = ["photo", "sample_id", "picture_label", "status", "message", "particles", "flagged_for_review",
                  "quality_problems", "background_type", "px_per_mm", "scale_source", "mm_per_px"]


def read_settings(path):
    """{photo file name: settings row} from the settings CSV (blank cells left out)."""
    if not path:
        return {}
    with open(path, newline="") as fh:
        return {r["photo"].strip(): {k.strip(): v.strip() for k, v in r.items() if k and v and v.strip()}
                for r in csv.DictReader(fh) if r.get("photo", "").strip()}


def plan(folder, settings, default_sample=None, metadata=None):
    """One job per photo: file, sample ID, photo number, metadata and printed-line length."""
    photos = sorted(p for p in Path(folder).iterdir() if p.suffix.lower() in PHOTO_TYPES)
    jobs, count = [], defaultdict(int)
    for p in photos:
        s = settings.get(p.name, {})
        sample = s.get("sample_id") or default_sample or p.stem
        count[sample] += 1
        meta = {k: s.get(k, (metadata or {}).get(k, "")) for k in METADATA}
        jobs.append({"path": p, "sample_id": sample, "photo": int(s.get("photo_number") or count[sample]),
                     "metadata": meta, "line_mm": float(s["line_mm"]) if s.get("line_mm") else None})
    return jobs


def run_batch(folder, out_dir, settings=None, default_sample=None, metadata=None, run=None):
    """Process every photo in `folder`; returns (all particle rows, report rows)."""
    if run is None:
        from .cli import run_grid as run  # cli imports this module's neighbours; import late
    out_dir = Path(out_dir)
    jobs = plan(folder, read_settings(settings), default_sample, metadata)
    rows, report = [], []
    for job in jobs:
        p = job["path"]
        label = f"{job['sample_id']}-P{job['photo']:02d}"
        rec = {"photo": p.name, "sample_id": job["sample_id"], "picture_label": label}
        photo_dir = out_dir / "photos" / p.stem
        try:
            got = run(p, photo_dir, job["sample_id"], job["photo"], job["metadata"], job["line_mm"])
        except (ValueError, OSError) as e:
            rec.update({"status": "refused", "message": " / ".join(str(e).splitlines())})
            report.append(rec)
            print(f"{p.name}: refused: {str(e).splitlines()[0]}", file=sys.stderr)
            continue
        info = json.loads((photo_dir / "run.json").read_text())
        problems = [q["code"] for q in info.get("quality", {}).get("problems", [])]
        rec.update({"status": "processed", "message": "", "particles": len(got),
                    "flagged_for_review": sum(bool(r["review_reason"]) for r in got),
                    "quality_problems": ";".join(problems), "background_type": info.get("background_type", ""),
                    "px_per_mm": info.get("px_per_mm", ""),
                    # mm_per_px includes any scale correction (paper edges or the 100 mm line); px_per_mm is the markers'
                    "scale_source": got[0]["scale_source"] if got else "", "mm_per_px": info.get("mm_per_px", "")})
        rows += got
        report.append(rec)
        print(f"{p.name}: {len(got)} particles", file=sys.stderr)
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, cols, data in (("particles.csv", COLUMNS, rows), ("summary.csv", SUMMARY_COLUMNS, build_summary(rows)),
                             ("batch_report.csv", REPORT_COLUMNS, report)):
        with open(out_dir / name, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
            w.writeheader()
            w.writerows(data)
    (out_dir / "NOTE.txt").write_text(NOTE + "\n")
    (out_dir / "batch.json").write_text(json.dumps({
        "mippr_version": __version__, "folder": str(folder), "settings": str(settings or ""),
        "processed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "photos": len(jobs), "processed": sum(r["status"] == "processed" for r in report),
        "refused": sum(r["status"] == "refused" for r in report), "particles": len(rows), "note": NOTE}, indent=2))
    return rows, report
