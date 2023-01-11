import types
import sys
import typing
import inspect
import logging
import cv2
import numpy as np
import nptyping as npt
from pathlib import Path
import h5darkframes as dark
from ..types import Configuration, Metadata

_logger = logging.getLogger("postprocess")


def darkframes(
    image: npt.NDArray, meta: Metadata, h5file: str = "/opt/nightskycam/darkframes.hdf5"
) -> npt.NDArray:

    h5file_ = Path(h5file)

    if not h5file_.is_file():
        raise FileNotFoundError(f"failed to find darkframes file: {h5file}")

    temperature = int(0.5 + meta["controllables"]["Temperature"] / 10.0)
    exposure = meta["controllables"]["Exposure"]
    param = (temperature, exposure)

    with dark.ImageLibrary(h5file_) as il:

        try:
            neighbors = il.get_interpolation_neighbors(param)
        except ValueError:
            neighbors = [il.get_closest(param)]
        if param in neighbors:
            darkframe, _ = il.get(param)
        else:
            darkframe = il.generate_darkframe(param, neighbors)
        subimage = dark.substract(image, darkframe)

    return subimage


def convert_color(
    image: npt.NDArray, meta: Metadata, conversion_code: str = "COLOR_BAYER_BG2BGR"
) -> npt.NDArray:

    try:
        code = getattr(cv2, conversion_code)
    except AttributeError:
        valid = ", ".join(
            [attr for attr in cv2.__dict__.keys() if attr.startswith("COLOR_")]
        )
        raise ValueError(
            f"{conversion_code} is not a valid cv2 conversion code. "
            f"Valid codes are: {valid}"
        )
    try:
        r = cv2.cvtColor(image, code)
    except Exception as e:
        raise e.__class__(f"failed to apply conversion code to the image: {e}")
    return r


def cv2_resize(
    image: npt.NDArray,
    meta: Metadata,
    ratio: float = 2.0,
    interpolation: str = "INTER_NEAREST",
) -> npt.NDArray:
    if interpolation not in dir(cv2):
        valid = ", ".join([inter for inter in dir(cv2) if inter.startswith("INTER")])
        raise ValueError(
            f"can not perform opencv2 interpolation {interpolation}. "
            f"Are valid: {valid}"
        )
    interpolation_ = getattr(cv2, interpolation)

    def _resize(
        arr: npt.NDArray, new_shape: typing.Tuple[int, int], interpolation
    ) -> npt.NDArray:
        return np.asarray(
            cv2.resize(arr, (new_shape[1], new_shape[0]), interpolation=interpolation)
        )

    new_shape = (
        int(image.shape[0] / ratio),
        int(image.shape[1] / ratio),
    )
    final_shape = (new_shape[0], new_shape[1], 1)
    resized_channels = [
        _resize(channel, new_shape, interpolation_).reshape(final_shape)
        for channel in np.dsplit(image, 3)
    ]
    return np.concatenate(resized_channels, axis=2)


def _list_functions() -> typing.List[types.FunctionType]:
    functions = [
        value
        for key, value in sys.modules[__name__].__dict__.items()
        if inspect.isfunction(value) and key != "apply" and not key.startswith("_")
    ]
    return functions


def _get_kwargs(f: typing.Callable) -> typing.List[str]:
    params = inspect.signature(f).parameters
    return [key for key, param in params.items() if param.default != inspect._empty]


def apply(
    image: npt.NDArray, meta: Metadata, postconfig: Configuration, dry_run: bool = False
) -> npt.NDArray:

    if "steps" not in postconfig.keys():
        _logger.info("no 'steps' key in the 'postprocess' configuration, skipping")
        return image

    steps = postconfig["steps"]

    if not steps:
        _logger.info("'steps' of 'postprocess' is empty: skipping")

    supported_fn = {f.__name__: f for f in _list_functions()}

    for fn in steps:

        if fn not in supported_fn:
            valid = ", ".join(supported_fn.keys())
            raise ValueError(
                f"the postprocess method '{fn}' is not supported. "
                f"Are supported: {valid}"
            )

        if fn not in postconfig:
            raise ValueError(
                f"the configuration for the postprocess method '{fn}' is missing"
            )

        kwargs = postconfig[fn]
        supported_kwargs = _get_kwargs(supported_fn[fn])

        for kwarg_key in kwargs.keys():
            if kwarg_key not in supported_kwargs:
                supported = ", ".join(supported_kwargs)
                raise ValueError(
                    f"the postprocess function '{fn}' does not support the argument '{kwarg_key}', "
                    f"supported: {supported}"
                )

        if not dry_run:
            try:
                _logger.info(f"applying {fn} with arguments {kwargs}")
                image = supported_fn[fn](image, meta, **kwargs)
            except Exception as e:
                raise RuntimeError(
                    f"failed to apply postprocess method '{fn}' with "
                    f"arguments '{kwargs}': {e}. "
                    f"(input image: shape {image.shape} dtype: {image.dtype})"
                )

    return image
