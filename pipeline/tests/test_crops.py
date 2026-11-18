"""Particle crops (crops.py): one transparent-background PNG per row, named in crop_file."""
import cv2
import numpy as np

from mippr.capture.sheet import Layout
from mippr.capture.synthetic import draw_particle, photograph, sheet_bgr
from mippr.cli import run_grid
from mippr.crops import crop_box, crop_particle


def test_crop_box_is_square_padded_and_clipped():
    assert crop_box(10, 20, 30, 10, (500, 500)) == (6, 6, 44, 44)  # side 30 + 2 x max(4, round(4.5) = 4), centred on (25, 25)
    assert crop_box(0, 0, 10, 10, (500, 500))[:2] == (0, 0)


def test_crop_keeps_pixels_and_blanks_background():
    img = np.full((60, 60, 3), 200, np.uint8)
    mask = np.zeros((60, 60), bool)
    mask[20:30, 25:40] = True
    img[mask] = (10, 20, 30)
    crop = crop_particle(img, mask)
    assert crop.shape[0] == crop.shape[1] and crop.shape[2] == 4
    on = crop[..., 3] == 255
    assert on.sum() == (10 + 2) * (15 + 2)  # the mask dilated by one pixel
    assert (crop[..., :3][crop[..., 3] == 255] == (10, 20, 30)).all(axis=1).sum() == 150


def test_run_writes_a_crop_per_row(tmp_path):
    lay = Layout("white_grid", "letter")
    img = sheet_bgr(lay, 200)
    draw_particle(img, lay, 200, "B2", "disc", 2.0, (40, 40, 200))
    draw_particle(img, lay, 200, "D5", "rect", 3.0, (200, 120, 40), aspect=3)
    path = tmp_path / "photo.png"
    cv2.imwrite(str(path), photograph(img, seed=3, out_width=2400))
    rows = run_grid(path, tmp_path / "out")
    assert [r["crop_file"] for r in rows] == [f"crops/{r['particle_ref']}.png" for r in rows]
    for r in rows:
        assert r["photo_file"] == "photo.png"
        crop = cv2.imread(str(tmp_path / "out" / r["crop_file"]), cv2.IMREAD_UNCHANGED)
        assert crop.shape[2] == 4 and crop[..., 3].max() == 255 and crop[..., 3].min() == 0
