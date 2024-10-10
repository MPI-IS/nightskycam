"""
Module defining the stretch method.
"""

from typing import Type, cast

import nptyping as npt
import numpy as np
from astropy import visualization
from astropy.visualization import ImageNormalize, MinMaxInterval
from auto_stretch.stretch import Stretch

stretch_methods = ("SqrtStretch", "AsinhStretch", "auto_stretch")
"""
The methods supported by the function [stretch](#stretch).
"""


def _recast(original_img: npt.NDArray, target_image: npt.NDArray) -> npt.NDArray:
    return (target_image * np.iinfo(original_img.dtype).max).astype(original_img.dtype)


def _stretch_image(
    img: npt.NDArray, stretch_class: Type[visualization.BaseStretch]
) -> npt.NDArray:
    interval = MinMaxInterval()
    vmin, vmax = interval.get_limits(img)
    norm = ImageNormalize(vmin=vmin, vmax=vmax, stretch=stretch_class())
    stretched = norm(img)
    r = _recast(img, stretched)
    return r


def stretch(image: npt.NDArray, method: str) -> npt.NDArray:
    """
    Apply a non-linear stretch to the image, using either the package
    astropy or auto-stretch. A stretch is usually used to make stars
    visually more salient.
    Currently only these methods are supported:

    - SqrtStretch
      ([astropy](https://docs.astropy.org/en/stable/api/astropy.visualization.SqrtStretch.html#sqrtstretch))
    - AsinhStretch
      ([astropy](https://docs.astropy.org/en/stable/api/astropy.visualization.AsinhStretch.html#asinhstretch))
    - [auto_stretch](https://github.com/LCOGT/auto_stretch)

    Args:
      image: image as a numpy array
      method: should be a member of '[stretch_methods](#stretch_methods)'

    Raises:
      ValueError: if method is not a member of '[stretch_methods](#stretch_methods)'

    Returns:
      the stretched image as numpy array
    """
    if method not in stretch_methods:
        raise ValueError(
            "Image processing configured to stretch the image using "
            f"{method}, but this method is not supported. "
            f"Supported methods: {', '.join(stretch_methods)}."
        )

    # auto stretch
    if method == "auto_stretch":
        auto_stretched = Stretch().stretch(image)
        return _recast(image, auto_stretched)

    # method from astropy
    instance = getattr(visualization, method)
    r = _stretch_image(image, instance)
    d = cast(npt.NDArray, r.data)
    return d
