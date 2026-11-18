"""Batch processing: a folder of sheet photos, a settings file, and a photo without a sheet."""
import csv
import json

import cv2
import numpy as np
import pytest

from mippr.batch import plan, read_settings
from mippr.capture.sheet import Layout
from mippr.capture.synthetic import draw_particle, photograph, sheet_bgr
from mippr.cli import main

DPI = 300


def sheet_photo(path, background, boxes, seed):
    lay = Layout(background, "letter")
    img = sheet_bgr(lay, DPI)
    for box in boxes:
        draw_particle(img, lay, DPI, box, "disc", 2.0, (40, 40, 200) if background != "black_grid" else (230, 230, 230))
    cv2.imwrite(str(path), photograph(img, seed=seed, k1=-0.02))


@pytest.fixture(scope="module")
def batch(tmp_path_factory):
    d = tmp_path_factory.mktemp("batch")
    photos = d / "photos"
    photos.mkdir()
    sheet_photo(photos / "a.jpg", "white_grid", ["B2", "C3"], 1)
    sheet_photo(photos / "b.jpg", "black_grid", ["D4"], 2)
    sheet_photo(photos / "c.jpg", "white_grid", ["E5"], 3)
    cv2.imwrite(str(photos / "no_sheet.jpg"), np.full((600, 800, 3), 200, np.uint8))  # no printed sheet
    (photos / "notes.txt").write_text("not a photo")
    with open(d / "settings.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["photo", "sample_id", "photo_number", "line_mm", "operator"])
        w.writerow(["a.jpg", "S1", "", "", "DS"])
        w.writerow(["b.jpg", "S1", "", "", "DS"])
        w.writerow(["c.jpg", "S2", "4", "100.5", ""])
    out = d / "out"
    main(["batch", str(photos), "--settings", str(d / "settings.csv"), "--out", str(out), "--lab", "Moore"])
    read = lambda name: list(csv.DictReader(open(out / name)))  # noqa: E731
    return out, read("particles.csv"), read("summary.csv"), read("batch_report.csv")


def test_plan_numbers_photos_within_each_sample(tmp_path):
    for name in ("x1.jpg", "x2.jpg", "y.png", "readme.md"):
        (tmp_path / name).write_bytes(b"")
    jobs = plan(tmp_path, {"y.png": {"sample_id": "S9"}}, default_sample="S1", metadata={"lab": "L"})
    assert [(j["path"].name, j["sample_id"], j["photo"]) for j in jobs] == [
        ("x1.jpg", "S1", 1), ("x2.jpg", "S1", 2), ("y.png", "S9", 1)]
    assert all(j["metadata"]["lab"] == "L" for j in jobs)


def test_settings_reader_drops_blank_cells(tmp_path):
    p = tmp_path / "s.csv"
    p.write_text("photo,sample_id,line_mm\na.jpg,S1,\n")
    assert read_settings(p) == {"a.jpg": {"photo": "a.jpg", "sample_id": "S1"}}


def test_every_photo_is_reported_and_the_sheetless_one_refused(batch):
    _, _, _, report = batch
    status = {r["photo"]: r["status"] for r in report}
    assert status == {"a.jpg": "processed", "b.jpg": "processed", "c.jpg": "processed", "no_sheet.jpg": "refused"}
    refused = next(r for r in report if r["photo"] == "no_sheet.jpg")
    assert "printed" in refused["message"]  # tells the user to use a printed background
    assert {r["photo"]: r["background_type"] for r in report if r["status"] == "processed"} == {
        "a.jpg": "white_grid", "b.jpg": "black_grid", "c.jpg": "white_grid"}


def test_combined_particles_and_one_summary_row_per_sample(batch):
    out, particles, summary, report = batch
    assert sorted(r["particle_ref"] for r in particles) == ["S1-P01-B2", "S1-P01-C3", "S1-P02-D4", "S2-P04-E5"]
    assert {r["sample_id"]: r["n_images"] for r in summary} == {"S1": "2", "S2": "1"}
    assert {r["sample_id"]: r["n_particles"] for r in summary} == {"S1": "3", "S2": "1"}
    assert all(r["lab"] == "Moore" for r in particles)
    assert {r["operator"] for r in particles if r["sample_id"] == "S1"} == {"DS"}
    c = next(r for r in particles if r["sample_id"] == "S2")
    assert c["scale_source"] == "user_corrected" and c["flag_scale"] == "True"  # line_mm 100.5 from the settings
    assert (out / "photos" / "a" / "overlay.png").exists()
    info = json.loads((out / "batch.json").read_text())
    assert (info["photos"], info["processed"], info["refused"], info["particles"]) == (4, 3, 1, 4)
