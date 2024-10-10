"""
Module defining the resize function.
"""

from typing import Tuple

import cv2
import numpy as np


def _interpolation(interpolation: str) -> int:
    if interpolation not in dir(cv2):
        valid = ", ".join([inter for inter in dir(cv2) if inter.startswith("INTER_")])
        raise ValueError(
            f"can not perform opencv2 interpolation {interpolation}. "
            f"Are valid: {valid}"
        )
    return getattr(cv2, interpolation)


def _resize(
    arr: np.ndarray, new_shape: Tuple[int, int], interpolation: str
) -> np.ndarray:
    interpolation_ = _interpolation(interpolation)
    return np.asarray(
        cv2.resize(arr, (new_shape[1], new_shape[0]), interpolation=interpolation_)
    )


def _simple_resize(
    image: np.ndarray,
    ratio: float = 2.0,
    interpolation: str = "INTER_NEAREST",
) -> np.ndarray:
    new_shape = (int(image.shape[0] / ratio), int(image.shape[1] / ratio))
    return _resize(image, new_shape, interpolation)


def _channel_resize(
    image: np.ndarray,
    ratio: float = 2.0,
    interpolation: str = "INTER_NEAREST",
) -> np.ndarray:
    new_shape = (
        int(image.shape[0] / ratio),
        int(image.shape[1] / ratio),
    )
    final_shape = (new_shape[0], new_shape[1], 1)
    resized_channels = [
        _resize(channel, new_shape, interpolation).reshape(final_shape)
        for channel in np.dsplit(image, 3)
    ]
    return np.concatenate(resized_channels, axis=2)


def resize(
    image: np.ndarray, ratio: float = 2.0, interpolation: str = "INTER_NEAREST"
) -> np.ndarray:
    """
    resize the image using the method 'resize'
    from opencv2
    """

    if len(image.shape) == 2:
        return _simple_resize(image, ratio, interpolation)
    return _channel_resize(image, ratio, interpolation)
