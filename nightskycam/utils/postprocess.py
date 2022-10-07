import types
import sys
import toml
import typing
import inspect
import logging
import cv2
import numpy as np
import nptyping as npt
from ..types import Configuration

_logger = logging.getLogger("postprocess")


def convert_color(
    image: npt.NDArray, conversion_code: str = "COLOR_BAYER_BG2BGR"
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


def np_rebin(
    image: npt.NDArray, ratio: float = 2.0
) -> npt.NDArray:

    def _rebin(
            arr: npt.NDArray,
            new_shape: typing.Tuple[int,int],
            original_type
    )->npt.NDArray:
        shape = (new_shape[0], arr.shape[0] // new_shape[0],
                 new_shape[1], arr.shape[1] // new_shape[1])
        return arr.reshape(shape).mean(-1,dtype=original_type).mean(1,dtype=original_type)

    new_shape = (
        int(image.shape[0]/ratio),
        int(image.shape[1]/ratio),
    )
    final_shape = (
        new_shape[0],
        new_shape[1],
        1
    )
    binned_channels = [
        _rebin(channel,new_shape, image.dtype).reshape(final_shape)
        for channel in np.dsplit(image,3)
    ]
    return np.concatenate(binned_channels,axis=2)



def _list_functions() -> typing.List[types.FunctionType]:
    functions = [
        value
        for key, value in sys.modules[__name__].__dict__.items()
        if inspect.isfunction(value) and key!="apply" and not key.startswith("_")
    ]
    return functions


def _get_kwargs(f: typing.Callable) -> typing.List[str]:
    params = inspect.signature(f).parameters
    return [key for key, param in params.items() if param.default != inspect._empty]


def apply(
    image: npt.NDArray, postconfig: Configuration, dry_run: bool = False
) -> typing.Tuple[npt.NDArray, str]:

    if "order" not in postconfig.keys():
        _logger.info("no 'order' key in the 'postprocess' configuration, skipping")
        return image, toml.dumps({"postprocess": None})

    order = postconfig["order"]

    if not order:
        _logger.info("'order' of 'postprocess' is empty: skipping")

    supported_fn = {f.__name__: f for f in _list_functions()}

    for fn in order:

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
                image = supported_fn[fn](image, **kwargs)
            except Exception as e:
                raise e.__class__(
                    f"failed to apply postprocess method '{fn}' with "
                    f"arguments '{kwargs}': {e}"
                )

    return image, toml.dumps(postconfig)
