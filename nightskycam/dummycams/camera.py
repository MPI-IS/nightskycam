"""
Module defining DummyCamera.
"""

from typing import Dict, List, Tuple

import numpy as np
from nightskyrunner.config import Config

from ..cams.camera import Camera


def _get_camera_like_image(
    camera_shape: Tuple[int, int] = (2822, 4144), dtype=np.uint16
) -> np.ndarray:
    """
    Returns an image, same format as the capture from
    a zwo asi camera.
    """

    rng = np.random.default_rng()
    if np.issubdtype(dtype, np.floating):
        return rng.random(camera_shape, dtype=dtype)
    elif np.issubdtype(dtype, np.integer):
        max_val = np.iinfo(dtype).max
        return rng.integers(low=0, high=max_val, size=camera_shape, dtype=dtype)
    else:
        raise ValueError(f"Unsupported dtype: {dtype}")


class DummyCamera(Camera):
    """
    The camera used by DummyCamRunner.
    It does not take picture, but generate an image with random
    pixels. The image is of shape 2822 x 4144 and of type int16.

    For testing purposes.
    """

    def __init__(self) -> None:
        self._config: Config = {}

    def configure(self, active: bool, config: Config) -> List[str]:
        self._config = config
        return []

    def picture(self) -> Tuple[np.ndarray, dict]:
        return _get_camera_like_image(), self._config

    def is_connected(self) -> bool:
        return True

    def get_info(self) -> Dict[str, str]:
        return {}
