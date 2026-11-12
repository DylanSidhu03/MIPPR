"""Dump the Python sheet layouts (pipeline/mippr/capture/sheet.py) to JSON for the JS parity test.

Run from the repo root: .venv/bin/python web/tests/dump_python_layout.py
Writes web/tests/fixtures/layouts.json (committed, so `node --test web/tests/` needs no Python).
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipeline"))
from mippr.capture.sheet import BACKGROUNDS, LAYOUT_VERSION, PAPERS, Layout, layout_from_marker_ids  # noqa: E402

OUT = Path(__file__).resolve().parent / "fixtures" / "layouts.json"
CUSTOM = [dict(box_mm=10.0, line_mm=0.3), dict(box_mm=7.3, margin_mm=6.0, gap_mm=5.0), dict(box_mm=5.0)]


def dump(lay):
    return {
        "options": {"background": lay.background, "paper": lay.paper, "boxMm": lay.box_mm, "lineMm": lay.line_mm,
                    "marginMm": lay.margin_mm, "markerMm": lay.marker_mm, "gapMm": lay.gap_mm,
                    "boxLabels": lay.box_labels, "labelZoneMm": list(lay.label_zone_mm)},
        "sizeMm": list(lay.size_mm),
        "cols": lay.cols,
        "rows": lay.rows,
        "gridOriginMm": list(lay.grid_origin_mm),
        "gridSizeMm": list(lay.grid_size_mm),
        "markerIds": lay.marker_ids(),
        "markerCornersMm": {str(k): v.tolist() for k, v in lay.marker_corners_mm().items()},
        "boxLabels": [[lay.box_label(r, c) for c in range(lay.cols)] for r in range(lay.rows)],
        "scaleLineMm": [list(p) for p in lay.scale_line_mm()],
        "patchesMm": {k: list(v) for k, v in lay.patches_mm().items()},
    }


def from_id(i):
    try:
        lay = layout_from_marker_ids([i])
        return [lay.background, lay.paper]
    except ValueError:
        return None


layouts = [Layout(bg, paper) for bg in BACKGROUNDS for paper in PAPERS]
layouts += [Layout(bg, paper, **kw) for kw in CUSTOM for bg in BACKGROUNDS[:1] for paper in PAPERS]
data = {
    "layoutVersion": LAYOUT_VERSION,
    "backgrounds": list(BACKGROUNDS),
    "papers": {k: list(v) for k, v in PAPERS.items()},
    "layouts": [dump(lay) for lay in layouts],
    "layoutFromMarkerId": {str(i): from_id(i) for i in range(50)},
}
OUT.parent.mkdir(exist_ok=True)
OUT.write_text(json.dumps(data, indent=1) + "\n")
print(f"Wrote {OUT.relative_to(ROOT)} ({len(layouts)} layouts)")
