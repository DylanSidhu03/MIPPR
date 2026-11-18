"""The shared model inputs and augmentation (training/common.py)."""
import math

import cv2
import numpy as np

from common import (AUGMENT_DEFAULTS, BACKGROUNDS, FEATURES, augment, feature_stats, feature_vector, image_array,
                    normalise_label, prepare_image)
from mippr.crops import crop_particle
from mippr.morphology.model import model_input


def _particle():
    img = np.full((80, 90, 3), 230, np.uint8)
    mask = np.zeros((80, 90), bool)
    cv2.ellipse(img, (40, 35), (18, 9), 30, 0, 360, (30, 90, 200), -1)
    cv2.ellipse(mask.view(np.uint8), (40, 35), (18, 9), 30, 0, 360, 1, -1)
    return img, mask


def test_prepare_image_is_model_input():
    img, mask = _particle()
    for size in (16, 64, 128):
        want, scale = model_input(img, mask, size)
        got = prepare_image(crop_particle(img, mask), size)
        assert np.array_equal(want, got)
        assert scale == crop_particle(img, mask).shape[1] / size


def test_image_array_is_rgb_channels_first():
    bgr = np.zeros((4, 4, 3), np.uint8)
    bgr[..., 2] = 255  # red
    a = image_array(bgr, [0.5] * 3, [0.25] * 3)
    assert a.shape == (3, 4, 4) and a.dtype == np.float32
    assert np.allclose(a[0], 2.0) and np.allclose(a[2], -2.0)


def test_augment_keeps_the_particle_and_its_colour():
    img, mask = _particle()
    crop = crop_particle(img, mask)
    area = (crop[..., 3] > 0).sum()
    hue = cv2.cvtColor(crop[..., :3], cv2.COLOR_BGR2HSV)[..., 0][crop[..., 3] > 0].mean()
    rng = np.random.default_rng(0)
    for _ in range(20):
        out = augment(crop, rng)
        alpha = out[..., 3] > 0
        assert out.shape[2] == 4 and out.shape[0] == out.shape[1]  # square, like a real crop
        assert 0.6 * area < alpha.sum() < 1.6 * area  # limited scaling (+ resampling)
        assert not alpha[0].any() and not alpha[-1].any() and not alpha[:, 0].any()  # padded, nothing cut off
        inner = cv2.erode(alpha.astype(np.uint8), np.ones((5, 5), np.uint8)).astype(bool)
        h = cv2.cvtColor(out[..., :3], cv2.COLOR_BGR2HSV)[..., 0][inner].mean()
        assert abs(h - hue) < 4  # no hue shift (OpenCV hue is 0-180)
    a = augment(crop, np.random.default_rng(5))
    b = augment(crop, np.random.default_rng(5))
    assert np.array_equal(a, b)
    same = augment(crop, rng, {k: 0 for k in AUGMENT_DEFAULTS} | {"rotate": False, "flip": False})
    assert (same[..., 3] > 0).sum() == area  # no change: only framed again round the (dilated) outline


def test_features():
    rows = [{"length_mm": "1", "width_mm": "0.5", "aspect_ratio": "1.2", "background_type": "white_grid"},
            {"length_mm": "3", "width_mm": "", "aspect_ratio": "2.0", "background_type": "black_grid"}]
    stats = feature_stats(rows)
    assert [s["name"] for s in stats] == [n for n, _ in FEATURES]
    v = feature_vector(rows[1], stats)
    assert v.shape == (len(FEATURES) + len(BACKGROUNDS),)
    names = [n for n, _ in FEATURES]
    assert v[names.index("width_mm")] == 0  # missing -> the training mean
    assert v[names.index("length_mm")] > 0 and math.isclose(stats[names.index("length_mm")]["mean"],
                                                             (math.log1p(1) + math.log1p(3)) / 2)
    assert list(v[-3:]) == [0, 1, 0]
    assert list(feature_vector({"background_type": "?"}, stats)[-3:]) == [0, 0, 0]


def test_normalise_label():
    assert normalise_label("Rubbery_Fragment") == "rubbery_fragment"
    assert normalise_label("Fibers") == "fiber"
    assert normalise_label("Sphere") == "pellet"
    assert normalise_label("unsure") is None and normalise_label("") is None
