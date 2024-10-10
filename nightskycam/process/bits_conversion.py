"""
Module defining the to_8bits function.
"""

import numpy as np
import numpy.typing as npt


def _bits_reduction(data: npt.NDArray, target: np.dtype) -> npt.NDArray:
    original_max = np.iinfo(data.dtype).max
    target_max = np.iinfo(target).max
    ratio = target_max / original_max
    return (data * ratio).astype(target)


def to_8bits(image: npt.NDArray) -> npt.NDArray:
    """
    Convert image to 8 bits (i.e. returns an array
    of dtype numpy uint8)
    """
    return _bits_reduction(image, np.dtype(np.uint8))
