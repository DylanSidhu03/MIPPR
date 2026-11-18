"""Fixtures for the end-to-end parity test: Python's run_grid on the quality test's good photos.

Writes web/tests/fixtures/pipeline.json: for each photo, the rows run_grid produces
(processed_at included, so the JS run can be given the same time) and run.json's key
fields. The photos themselves are the quality_*.png fixtures (dump_python_quality.py).

    .venv/bin/python web/tests/dump_python_pipeline.py
"""
import json
import math
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipeline"))
from mippr.cli import run_grid  # noqa: E402

FIX = ROOT / "web" / "tests" / "fixtures"
CASES = [("quality_white_grid.png", {"sample_id": "S1", "photo": 1, "line_mm": None}),
         ("quality_black_grid.png", {"sample_id": "S1", "photo": 2, "line_mm": None}),
         ("quality_checkerboard.png", {"sample_id": "S2", "photo": 1, "line_mm": 100.4})]


def clean(v):
    if isinstance(v, float) and not math.isfinite(v):
        return {"float": repr(v)}
    return v


def main():
    out = []
    for name, kw in CASES:
        with tempfile.TemporaryDirectory() as d:
            rows = run_grid(FIX / name, d, kw["sample_id"], kw["photo"], {"lab": "Moore", "operator": "DS"},
                            kw["line_mm"])
            run = json.loads((Path(d) / "run.json").read_text())
        out.append({"file": name, **kw, "metadata": {"lab": "Moore", "operator": "DS"},
                    "rows": [{k: clean(v) for k, v in r.items()} for r in rows],
                    "run": {k: run[k] for k in ("background_type", "markers_found", "px_per_mm", "mm_per_px",
                                                "white_balance", "quality")}})
    (FIX / "pipeline.json").write_text(json.dumps(out, indent=1))
    print(f"{sum(len(c['rows']) for c in out)} rows from {len(out)} photos -> {FIX / 'pipeline.json'}")


if __name__ == "__main__":
    main()
