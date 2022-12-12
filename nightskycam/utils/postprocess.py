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
        image: npt.NDArray, meta: Metadata,
        h5file: str = "/opt/nightskycam/darkframes.hdf5"
)->npt.NDArray:

   
    h5file_ = Path(h5file)
    
    if not h5file_.is_file():
        raise FileNotFoundError(
            f"failed to find darkframes file: {h5file}"
        )

    try:
        library = dark.ImageLibrary(h5file_)
    except Exception as e:
        raise ValueError(
            f"failed to open darkframes file {h5file}: {e}"
        )

    lib_controllables = library.controllables()

    try:
        meta_controllables = meta["controllables"]
    except KeyError:
        raise ValueError(
            f"failed to substract darkframes: meta data are missing the key 'controllables'"
        )


    # hacky !
    # for zwo asi camera, the controllable is "TargetTemp", but the value
    # we are interested in is "Temperature". TargetTemp is in degree celcius,
    # but Temperature in "deci" degree celcius
    if "TargetTemp" in meta_controllables:
        if "Temperature" in meta_controllables:
            meta_controllables["TargetTemp"] = int( (meta_controllables["Temperature"] / 10.) + 0.5)
    
    for lib_controllable in lib_controllables:
        if lib_controllable not in meta_controllables:
            raise ValueError(
                f"failed to substract darkframes. The required controllable {controllable} "
                f"is not part of the metadata of the image."
            )

    controls = {controllable:meta_controllables[controllable] for controllable in lib_controllables}

    try:
        darkframe,_ = library.get(controls,dark.GetType.neighbors)
    except Exception as e:
        raise ValueError(
            f"failed to get darkframe for controls {controls}: {e}"
        )

    if darkframe.shape != image.shape:
        raise ValueError(
            f"failed to substract darkframe: darkframe is of shape {darkframe.shape} "
            f"while image is of shape {image.shape}"
        )

    if darkframe.dtype != image.dtype:
        raise ValueError(
            f"failed to substract darkframe: darkframe is of data type {darkframe.dtype} "
            f"while image is of data type {image.dtype}"
        )

    im32 = image.astype(np.int32)
    dark32 = image.astype(np.int32)

    sub32 = im32 - dark32
    sub32[sub32<0]=0

    return sub32.astype(image.dtype)
        


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
    image: npt.NDArray, meta: Metadata, ratio: float = 2.0, interpolation: str = "INTER_NEAREST"
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
                raise e.__class__(
                    f"failed to apply postprocess method '{fn}' with "
                    f"arguments '{kwargs}': {e}. "
                    f"(input image: shape {image.shape} dtype: {image.dtype})"
                )

    return image
