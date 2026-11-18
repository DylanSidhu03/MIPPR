"""Fixtures for the review-rules parity test: Python's review/corrections.py on pipeline rows.

Writes web/tests/fixtures/review.json:
- rows: run_grid's rows for quality_white_grid.png (processed_at fixed, so the file is the same on every run);
- sequences: decisions applied one at a time to one row, with the row (or the error) after each;
- apply_all: decision lists applied with apply_all, with the rows (or the error) out;
- times: ISO 8601 strings with Python's reading (microseconds since 1970 UTC) or the error;
- queues: review_queue orders on mixed rows, including CSV-style string values;
- outlines: edit_outline cases re-measured with the photo's MeasureContext (the JS test rebuilds it).

    .venv/bin/python web/tests/dump_python_review.py
"""
import dataclasses
import json
import math
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipeline"))
from mippr.capture.calibration import white_balance  # noqa: E402
from mippr.capture.sheet import find_sheet  # noqa: E402
from mippr.cli import run_grid  # noqa: E402
from mippr.review.corrections import (Decision, MeasureContext, apply, apply_all, parse_time,  # noqa: E402
                                      review_queue)
from mippr.segmentation.grid import GridSegmentParams, background_image, box_of, line_band, segment_grid  # noqa: E402

FIX = ROOT / "web" / "tests" / "fixtures"
PHOTO = FIX / "quality_white_grid.png"
SAMPLE = {"sample_id": "S1", "photo": 1, "metadata": {"lab": "Moore", "operator": "DS"}}
PROCESSED_AT = "2026-11-18T00:00:00+00:00"
T0 = "2026-11-12T10:00:00Z"


def clean(v):
    if isinstance(v, float) and not math.isfinite(v):
        return {"float": repr(v)}
    return v


def row_json(r):
    return {k: clean(v) for k, v in r.items()}


def d(ref, action, at=T0, reviewer="DS", role="expert", **kw):
    return Decision(ref, action, reviewer, role, at, **kw)


def run(fn):
    """{"row"/"rows": result} or {"error": message, "type": exception name}."""
    try:
        return fn()
    except (ValueError, NotImplementedError) as e:
        return {"error": str(e), "type": type(e).__name__}


def sequence(rows, ref, decisions, context=None):
    row = next(r for r in rows if r["particle_ref"] == ref)
    steps = []
    for dec in decisions:
        res = run(lambda: {"row": apply(row, dec, context)})
        steps.append(res if "error" in res else {"row": row_json(res["row"])})
        if "error" in res:
            break
        row = res["row"]
    return {"ref": ref, "decisions": [dataclasses.asdict(x) for x in decisions], "context": context is not None,
            "steps": steps}


def context_for(path, params=GridSegmentParams()):
    """The same steps as cli.run_grid, kept to build the MeasureContext (as tests/test_review.py does)."""
    photo = cv2.imread(str(path))
    sheet = find_sheet(photo)
    lay, ppm = sheet.layout, sheet.px_per_mm
    rect = sheet.rectify_grid(photo)
    gains, _ = white_balance(sheet, photo)
    balanced = np.clip(rect.astype(np.float32) * gains, 0, 255).astype(np.uint8)
    labels, diff, _ = segment_grid(rect, lay, ppm, params)
    band, _, outer = line_band(lay, ppm, labels.shape, params.line_margin_mm)
    near_line = cv2.dilate(band.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)
    ctx = MeasureContext(image=rect, mm_per_px=1.0 / ppm,
                         background=background_image(balanced, lay, ppm, params.inset_frac), diff=diff,
                         color_img=balanced, line_mask=near_line,
                         box_fn=lambda x, y: lay.box_label(*box_of(lay, ppm, x, y)),
                         edge_fraction=params.edge_fraction, edge_margin_px=int(np.ceil(outer)) + 2)
    return ctx, labels


def polygon(mask):
    contours, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    return max(contours, key=len).reshape(-1, 2).tolist()


def main():
    with tempfile.TemporaryDirectory() as tmp:
        rows = run_grid(PHOTO, tmp, SAMPLE["sample_id"], SAMPLE["photo"], SAMPLE["metadata"])
    for r in rows:
        r["processed_at"] = PROCESSED_AT
    b2, f7, k9 = "S1-P01-B2", "S1-P01-F7", "S1-P01-K9"

    sequences = [
        sequence(rows, b2, [d(b2, "confirm")]),
        sequence(rows, b2, [d(b2, "reject"), d(b2, "confirm", "2026-11-12T10:01:00Z")]),
        sequence(rows, b2, [d(b2, "relabel", color_label="pink", morphology_label="film"),
                            d(b2, "relabel", color_label="orange", reviewer="AB", role="community"),
                            d(b2, "relabel", color_label="red"),  # back to the prediction
                            d(b2, "confirm"),  # the morphology correction still stands
                            d(b2, "relabel", morphology_label="fragment"),
                            d(b2, "confirm")]),
        sequence(rows, b2, [d(b2, "relabel", color_label="red")]),  # relabel to what it is: a confirmation
        sequence(rows, f7, [d(f7, "relabel", color_label="unknown"), d(f7, "confirm"), d(f7, "reject"),
                            d(f7, "confirm")]),
        sequence(rows, f7, [d(f7, "tag", tags={"tar_like": True, "flag_bundle": True}),
                            d(f7, "tag", tags={"flag_bundle": False}), d(f7, "confirm"),
                            d(f7, "tag", tags={"tar_like": False})]),
        sequence(rows, k9, [d(k9, "relabel", morphology_label="pellet"), d(k9, "tag", tags={"flag_bundle": True}),
                            d(k9, "reject")]),
    ]
    errors = [
        d(b2, "delete"), d(b2, "approve"), d("S1-P01-Z9", "confirm"), d(b2, "confirm", reviewer="  "),
        d(b2, "confirm", reviewer=""), d(b2, "confirm", role="admin"), d(b2, "confirm", at="yesterday"),
        d(b2, "confirm", at="2026-02-30T10:00:00Z"), d(b2, "relabel"), d(b2, "relabel", color_label="teal"),
        d(b2, "relabel", morphology_label="blob"), d(b2, "relabel", color_label="red", morphology_label="it's"),
        d(b2, "tag"), d(b2, "tag", tags={"sticky": True}), d(b2, "tag", tags={"tar_like": True, "sticky": 1}),
        d(b2, "tag", tags={"tar_like": 1}), d(b2, "tag", tags={"tar_like": "True"}), d(b2, "split"),
        d(b2, "merge"), d(b2, "edit_outline", outline=[[1, 1], [5, 1], [3, 4]]),
    ]
    sequences += [sequence(rows, b2, [e]) for e in errors]
    # With a context, the polygon is checked before anything is measured.
    sequences += [sequence(rows, b2, [d(b2, "edit_outline", outline=o)], context=object())
                  for o in ([], [[1, 1], [2, 2]], None)]
    sequences += [sequence(rows, b2, [d(b2, "relabel", color_label="blue"), d(b2, "reject", role="boss")])]

    def all_case(ds, rs=rows):
        res = run(lambda: {"rows": apply_all(rs, ds)})
        return {"rows": [row_json(r) for r in rs] if rs is not rows else None,
                "decisions": [dataclasses.asdict(x) for x in ds],
                **({"out": [row_json(r) for r in res["rows"]]} if "rows" in res else res)}

    apply_alls = [
        all_case([d(b2, "relabel", "2026-11-12T11:00:00Z", color_label="blue"),
                  d(b2, "relabel", "2026-11-12T10:00:00+00:00", color_label="pink"),
                  d(f7, "reject", "2026-11-12T11:30:00+01:00"),  # 10:30 UTC
                  d(f7, "confirm", "2026-11-12 10:15:00"),  # no zone: UTC
                  d(k9, "confirm", "2026-11-12T10:00:00.5Z"),
                  d(k9, "relabel", "2026-11-12T10:00:00.5Z", color_label="grey")]),  # tie: given order
        all_case([d(b2, "confirm"), d("S1-P01-Q1", "confirm")]),
        all_case([d(b2, "confirm")], [rows[0], {**rows[1], "particle_ref": b2}]),
        all_case([d(b2, "confirm"), d(f7, "confirm", at="soon")]),
        all_case([]),
    ]

    times = ["2026-11-12", "20261112", "2026-11-12T10", "2026-11-12T10:00", "2026-11-12T1000",
             "2026-11-12T10:00:00.5Z", "2026-11-12T10:00:00.1234567Z", "2026-11-12T10:00:00,5",
             "2026-11-12 10:00:00", "2026-11-12x10:00", "2026-W46-4", "2026W464", "2026-W46", "2026W46",
             "2026W464T10", "2026-W46T10", "2026-316", "2026-11-12T10:00:00+0100", "2026-11-12T10:00:00+01",
             "2026-11-12T10:00:00-01:30:15", "2026-11-12T10:00:00+01:30:15.5", "2026-11-12T24:00:00",
             "2026-02-30", "2024-02-29", "2026-11-12T10:00:00z", "2026-11-12T10:00Z", "2026-11-12T10Z", "2026-11",
             "yesterday", "", "2026-11-12T10:00:00.", "2026-11-12T10:00:60", "+2026-11-12", "2026-11-12T",
             "2026-W46-", "2026-11-12T10:0000", "2026-11-12T1000:00", "2026-11-12T10:00:00+1",
             "2026-11-12T10:00:00+", "2026111", "2026-11-12T10:00:00-00:00", "2026-11-12T10:00:00.5+01",
             "2026-11-12T10.5", "2026-11-12T10:30.5", "2026-11-12T10:00:00+24:00", "2026-11-12T10:00:00+23:59",
             "2020-W53-7", "2026-W53-1", "0001-01-01", "0000-01-01", "9999-12-31T23:59:59.999999",
             "1969-12-31T23:59:59Z", "2026-11-12T10:00:00.000Z"]
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    time_cases = [{"at": s, **run(lambda: {"micros": str((parse_time(s) - epoch) // timedelta(microseconds=1))})}
                  for s in times]

    mixed = [dict(r) for r in rows] + [dict(r) for r in rows]
    for i, r in enumerate(mixed):
        r["particle_ref"] = f"R{i}"
    mixed[0].update(review_status="rejected")
    mixed[1].update(review_status="confirmed", review_reason="edge")
    mixed[2].update(color_confidence="0.2")  # flagged (size_uncertain), as read from a CSV
    mixed[3].update(review_status="", flag_low_confidence="True", review_reason="", color_confidence="",
                    morphology_confidence="")  # flagged, no confidence: 1.0
    mixed[4].update(review_status="corrected")
    mixed[5].update(review_reason="", morphology_confidence="0.5", color_confidence=" 0.5 ")  # tie with R0's 0.5
    extra = [{**rows[0], "particle_ref": "R6", "color_confidence": "abc", "morphology_confidence": None},
             {**rows[0], "particle_ref": "R7", "review_status": None, "color_confidence": True},
             {**rows[0], "particle_ref": "R8", "color_confidence": "1_0e-1"},
             {**rows[0], "particle_ref": "R9", "review_reason": "line", "morphology_confidence": "-inf"},
             {**rows[0], "particle_ref": "R10", "flag_low_confidence": True, "color_confidence": 0.3},
             {**rows[0], "particle_ref": "R11", "flag_low_confidence": "False", "color_confidence": "0.30"}]
    queues = []
    for qs in (mixed, mixed + extra, list(reversed(mixed + extra)), [dict(r) for r in rows]):
        queues.append({"rows": [row_json(r) for r in qs], "order": [r["particle_ref"] for r in review_queue(qs)]})

    ctx, labels = context_for(PHOTO)
    by_ref = {r["particle_ref"]: r for r in rows}
    outlines = []
    for ref in (b2, f7, k9):  # the pipeline's own mask gives back the pipeline's numbers
        row = by_ref[ref]
        lbl = labels[int(round(row["centroid_y_px"])), int(round(row["centroid_x_px"]))]
        outlines.append(sequence(rows, ref, [d(ref, "edit_outline", outline=polygon(labels == lbl))], ctx))
    # The reviewer cuts B2's outline in half after correcting its morphology.
    row = by_ref[b2]
    half = labels == labels[int(round(row["centroid_y_px"])), int(round(row["centroid_x_px"]))]
    xs = np.nonzero(half.any(axis=0))[0]
    half[:, (xs.min() + xs.max()) // 2:] = False
    outlines.append(sequence(rows, b2, [d(b2, "relabel", morphology_label="film"),
                                        d(b2, "edit_outline", "2026-11-12T10:05:00Z", outline=polygon(half)),
                                        d(b2, "confirm", "2026-11-12T10:06:00Z")], ctx))
    # A hand-drawn quadrilateral round K9 (flat list of float vertices), and two outlines that can't be measured.
    kx, ky = by_ref[k9]["centroid_x_px"], by_ref[k9]["centroid_y_px"]
    outlines.append(sequence(rows, k9, [d(k9, "edit_outline", outline=[kx - 20.5, ky - 18, kx + 21.4, ky - 15.5,
                                                                      kx + 18, ky + 22.5, kx - 17.6, ky + 19])], ctx))
    outlines.append(sequence(rows, k9, [d(k9, "edit_outline", outline=[1.0, 2.0, 3.0, 4.0])], ctx))
    outlines.append(sequence(rows, k9, [d(k9, "edit_outline", outline=[[-50, -50], [-10, -50], [-30, -10]])], ctx))

    out = {"file": PHOTO.name, **SAMPLE, "processed_at": PROCESSED_AT, "rows": [row_json(r) for r in rows],
           "sequences": sequences, "apply_all": apply_alls, "times": time_cases, "queues": queues,
           "outlines": outlines}
    (FIX / "review.json").write_text(json.dumps(out, indent=1))
    print(f"{len(sequences)} sequences, {len(apply_alls)} apply_all cases, {len(time_cases)} times, "
          f"{len(queues)} queues, {len(outlines)} outline cases -> {FIX / 'review.json'}")


if __name__ == "__main__":
    main()
