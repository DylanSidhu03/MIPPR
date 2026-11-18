"""build_dataset.py on hand-made runs (particles.csv + tiny crops) and on a real pipeline run."""
import csv
import json

import cv2
import numpy as np
import pytest

from build_dataset import assign_splits, build, choose_label
from common import read_manifest
from mippr.export import COLUMNS


def _row(sample, photo_n, box, **kw):
    label = f"{sample}-P{photo_n:02d}"
    r = {c: "" for c in COLUMNS}
    r.update({"sample_id": sample, "picture_label": label, "image_id": f"{sample.lower()}{photo_n}-abcd1234",
              "photo_file": f"{sample.lower()}_{photo_n}.jpg", "particle_id": box, "particle_ref": f"{label}-{box}",
              "crop_file": f"crops/{label}-{box}.png", "background_type": "white_grid", "review_status": "auto",
              "morphology_label": "fragment", "morphology_source": "rule", "aspect_ratio": "1.3", "feret_ratio": "1.5",
              "circularity": "0.8", "roundness": "0.7", "solidity": "0.9", "solidity_subpixel": "0.95",
              "opacity": "0.9", "length_mm": "2.0", "width_mm": "1.4", "area_mm2": "2.1"})
    r.update(kw)
    return r


def write_run(d, rows, make_crops=True):
    d.mkdir(parents=True, exist_ok=True)
    (d / "crops").mkdir(exist_ok=True)
    with open(d / "particles.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(rows)
    for i, r in enumerate(rows):
        if make_crops and r["crop_file"]:
            img = np.zeros((12, 12, 4), np.uint8)
            img[3:9, 3:9] = (40 + i, 80, 200, 255)
            cv2.imwrite(str(d / r["crop_file"]), img)


def write_labels(path, rows):
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["photo", "sheet", "box", "morphology", "colour", "second_colour", "tar_like", "length_mm",
                    "width_mm", "labeller", "notes"])
        for r in rows:
            w.writerow(r)


@pytest.fixture
def runs(tmp_path):
    a = [
        _row("S1", 1, "A1", review_status="confirmed", morphology_label="pellet", reviewed_by="DS",
             reviewer_role="expert"),
        _row("S1", 1, "A2", review_status="corrected", morphology_label="rubbery_fragment",
             morphology_label_original="fragment", reviewed_by="DS", reviewer_role="community"),
        _row("S1", 1, "A3", review_status="rejected", morphology_label="foam", reviewed_by="DS",
             reviewer_role="expert"),
        _row("S1", 1, "A4"),  # auto: no label unless a label sheet has it
        # a split: the original B1 is rejected, B1-1 (no crop yet) and B1-2 (crop) replace it
        _row("S1", 1, "B1", review_status="rejected", reviewed_by="DS", reviewer_role="expert"),
        _row("S1", 1, "B1-1", crop_file="", review_status="corrected", morphology_label="fragment",
             derived_from="S1-P01-B1", reviewed_by="DS", reviewer_role="expert", outline_edited="True"),
        _row("S1", 1, "B1-2", review_status="corrected", morphology_label="foam", derived_from="S1-P01-B1",
             reviewed_by="DS", reviewer_role="expert", outline_edited="True"),
        _row("S1", 1, "C1", review_status="confirmed", morphology_label="other", reviewed_by="DS",
             reviewer_role="expert"),
        _row("S1", 1, "D1-1"), _row("S1", 1, "D1-2"),  # two blobs in one box
    ]
    b = [_row("S2", 1, "A1"), _row("S2", 1, "A2"), _row("S2", 1, "A3")]
    c = [_row("S3", 1, "A1", review_status="confirmed", morphology_label="pellet", reviewer_role="expert"),
         _row("S3", 1, "A2", review_status="confirmed", morphology_label="fragment", reviewer_role="expert")]
    write_run(tmp_path / "runA", a)
    write_run(tmp_path / "runB", b)
    write_run(tmp_path / "runC", c)
    labels = tmp_path / "advisor_labels.csv"
    write_labels(labels, [
        ["EXAMPLE_white_grid_1.jpg", "white_grid", "A1", "fragment", "", "", "", "", "", "AB", "example"],
        ["s1_1.jpg", "white_grid", "A4", "Foam", "", "", "", "", "", "AB", ""],       # by photo_file
        ["S1-P01", "white_grid", "B1", "fragment", "", "", "", "", "", "AB", ""],     # by picture_label: box B1 -> B1-1, B1-2
        ["s1_1.jpg", "white_grid", "D1", "fragment", "", "", "", "", "", "AB", ""],   # two blobs: unclear
        ["s1_1", "white_grid", "A1", "fragment", "", "", "", "", "", "AB", ""],       # by stem; disagrees with review
        ["s2_1.jpg", "white_grid", "A1", "Rubbery fragment", "", "", "", "", "", "AB", ""],
        ["s2_1.jpg", "white_grid", "A2", "Fibers", "", "", "", "", "", "AB", ""],
        ["s2_1.jpg", "white_grid", "A3", "unsure", "", "", "", "", "", "AB", ""],
        ["s2_1.jpg", "white_grid", "Z9", "fragment", "", "", "", "", "", "AB", ""],   # no such box
    ])
    return tmp_path, labels


def by_ref(dataset):
    rows, info = read_manifest(dataset)
    return {r["particle_ref"]: r for r in rows}, info


def test_labels_sources_and_skips(runs):
    d, labels = runs
    info = build([d / "runA", d / "runB", d / "runC"], d / "ds", [labels], fractions=(1, 0, 0))
    m, info2 = by_ref(d / "ds")
    assert info == info2 | {}  # what build returns is what it wrote
    # review labels; a box-label sheet wins over a review of the same role, an expert over a community reviewer
    assert m["S1-P01-A2"]["label"] == "rubbery_fragment" and m["S1-P01-A2"]["labeller_role"] == "community"
    assert m["S1-P01-A2"]["weight"] == "0.5" and m["S1-P01-A2"]["rule_label"] == "fragment"
    assert m["S3-P01-A1"]["label"] == "pellet"
    assert m["S1-P01-A4"]["label"] == "foam" and m["S1-P01-A4"]["source"] == "labels:advisor_labels.csv"
    assert m["S2-P01-A1"]["label"] == "rubbery_fragment"
    assert m["S2-P01-A2"]["label"] == "fiber"  # the lab's names are mapped (lab_sheets.lab_shape)
    # split pieces: the one with a crop is used; the rejected original never
    assert m["S1-P01-B1-2"]["label"] == "foam" and m["S1-P01-B1-2"]["derived_from"] == "S1-P01-B1"
    assert "S1-P01-B1" not in m and "S1-P01-B1-1" not in m
    assert "S1-P01-A3" not in m  # rejected
    assert "S1-P01-C1" not in m  # "other" is left out
    assert "S1-P01-A1" not in m  # two expert labels disagree (pellet vs fragment)
    assert "S2-P01-A3" not in m and "S1-P01-D1-1" not in m
    s = info["skipped"]
    assert s["conflict"] == 1 and s["label_other"] == 1 and s["no_crop"] == 1 and s["label_unknown"] == 1
    assert s["label_box_has_several_particles"] == 2  # B1 (B1-1 and B1-2 kept) and D1
    assert s["label_not_matched"] == 1
    # crops are copied, and features come along
    for r in m.values():
        assert (d / "ds" / r["crop"]).exists() and r["length_mm"] == "2.0"
    assert len(info["manifest_sha256"]) == 64


def test_split_by_sample_gold_and_kept_splits(runs, tmp_path):
    d, labels = runs
    gold = tmp_path / "gold.txt"
    gold.write_text("# gold set\nS3-P01-A1\n")
    build([d / "runA", d / "runB", d / "runC"], d / "ds", [labels], gold=gold)
    m, info = by_ref(d / "ds")
    assert m["S3-P01-A1"]["split"] == "gold"
    assert m["S3-P01-A2"]["split"] == "excluded"  # same sample as a gold particle
    per_sample = {}
    for r in m.values():
        per_sample.setdefault(r["sample_id"], set()).add(r["split"])
    assert all(len(v) == 1 for k, v in per_sample.items() if k != "S3")  # never split within a sample
    assert info["sample_splits"]["S3"] == "gold"
    # a later build keeps each sample's split, even with other fractions
    prev = d / "ds" / "manifest.json"
    build([d / "runA", d / "runB", d / "runC"], d / "ds2", [labels], gold=gold, keep_splits=prev, fractions=(0, 0, 1))
    m2, info2 = by_ref(d / "ds2")
    assert {r["particle_ref"]: r["split"] for r in m2.values()} == {r["particle_ref"]: r["split"] for r in m.values()}
    # whole samples can be gold too
    gold.write_text("sample_id:S2\n")
    build([d / "runA", d / "runB", d / "runC"], d / "ds3", [labels], gold=gold)
    m3, _ = by_ref(d / "ds3")
    assert {r["split"] for r in m3.values() if r["sample_id"] == "S2"} == {"gold"}
    assert "gold" not in {r["split"] for r in m3.values() if r["sample_id"] != "S2"}


def test_rebuild_gives_the_same_manifest(runs):
    d, labels = runs
    a = build([d / "runA", d / "runB"], d / "x", [labels])
    b = build([d / "runA", d / "runB"], d / "y", [labels])
    assert a["manifest_sha256"] == b["manifest_sha256"]


def test_assign_splits():
    s = assign_splits([f"S{i}" for i in range(20)], seed=1)
    assert set(s.values()) == {"train", "val", "test"}
    assert sum(v == "train" for v in s.values()) == 14
    small = assign_splits(["a", "b", "c"])
    assert sorted(small.values()) == ["test", "train", "val"]
    assert assign_splits(["a", "b"], keep={"a": "test"})["a"] == "test"


def test_choose_label():
    assert choose_label([{"raw": "Fibre", "role": "expert", "source": "review", "labeller": ""}])[0]["label"] == "fiber"
    assert choose_label([{"raw": "", "role": "expert", "source": "review", "labeller": ""}]) == (None, "label_unknown")
    c, why = choose_label([{"raw": "fragment", "role": "community", "source": "review", "labeller": ""},
                           {"raw": "foam", "role": "expert", "source": "review", "labeller": ""}])
    assert c["label"] == "foam" and why is None


def test_batch_duplicates_prefer_the_reviewed_copy(tmp_path):
    """A batch folder has the combined particles.csv and each photo's own; the reviewed copy wins."""
    photo = tmp_path / "batch" / "photos" / "s1_1"
    write_run(photo, [_row("S1", 1, "A1")])
    top = _row("S1", 1, "A1", crop_file="photos/s1_1/crops/S1-P01-A1.png", review_status="confirmed",
               morphology_label="pellet", reviewer_role="expert")
    with open(tmp_path / "batch" / "particles.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS)
        w.writeheader()
        w.writerow(top)
    info = build([tmp_path / "batch"], tmp_path / "ds", fractions=(1, 0, 0))
    m, _ = by_ref(tmp_path / "ds")
    assert info["n_particles"] == 1 and m["S1-P01-A1"]["label"] == "pellet"


def test_from_a_real_pipeline_run(tmp_path):
    """Synthetic sheet photos through run_grid, labelled by what was drawn; one particle rejected by review."""
    from synthetic import make_runs
    runs, labels, gold = make_runs(tmp_path / "syn", n_photos=2, per_class=1)
    first = sorted(runs.iterdir())[0] / "particles.csv"
    with open(first, newline="") as fh:
        rows = list(csv.DictReader(fh))
    rows[0]["review_status"] = "rejected"
    with open(first, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    info = build([runs], tmp_path / "ds", [labels], gold=gold)
    m, _ = by_ref(tmp_path / "ds")
    assert info["n_particles"] == 5  # 2 photos x 3 classes, less the rejected one
    assert rows[0]["particle_ref"] not in m
    assert {r["split"] for r in m.values() if r["sample_id"] == "SYN02"} == {"gold"}
    assert {r["label"] for r in m.values()} == {"pellet", "fragment", "rubbery_fragment"}
    for r in m.values():
        assert r["background_type"] in ("white_grid", "black_grid") and float(r["length_mm"]) > 1
    assert json.loads((tmp_path / "ds" / "manifest.json").read_text())["skipped"].get("label_not_matched", 0) == 1
