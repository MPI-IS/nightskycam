"""
Module for testing [nightskycam.process]()
"""

from typing import Union

import numpy as np
from nightskycam.process.bits_conversion import to_8bits
from nightskycam.process.debayer import debayer
from nightskycam.process.resize import resize

np_type = Union[np.uint8, np.uint16]

_camera_shape = (2822, 4144)


def _get_camera_like_image() -> np.ndarray:
    """
    Returns an image, same format as the capture from
    a zwo asi camera.
    """
    return np.ndarray(_camera_shape, dtype=np.uint16)


def test_debayer():
    """
    Test the debayer function
    """
    img = _get_camera_like_image()
    dby = debayer(img)
    assert dby.shape == (img.shape[0], img.shape[1], 3)


def test_resize():
    """
    Test the resize function, on both raw and debayered images
    """
    img = _get_camera_like_image()
    resized = resize(img, ratio=2.0)
    assert resized.shape == (int(_camera_shape[0] / 2.0), int(_camera_shape[1] / 2.0))
    dby = debayer(img)
    resized = resize(dby, ratio=2.0)
    assert resized.shape == (
        int(_camera_shape[0] / 2.0),
        int(_camera_shape[1] / 2.0),
        3,
    )


def _test_to_8_bits(img: np.ndarray):
    img8bits = to_8bits(img)
    assert img8bits.dtype == np.uint8
    assert img8bits.shape == img.shape


def test_to_8_bits():
    """
    Test the to_8bits function
    """
    img = _get_camera_like_image()
    _test_to_8_bits(img)
    resized = resize(img, ratio=2.0)
    _test_to_8_bits(resized)
    dby = debayer(img)
    _test_to_8_bits(dby)
    resized = resize(dby, ratio=2.0)
    _test_to_8_bits(resized)
