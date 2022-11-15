import typing
import nptyping as npt
import camera_zwo_asi
from pathlib import Path
from ..cameras.camera import Camera
from ..cameras.dummy_camera import DummyCamera
from .picture_thread import PictureThread
from ..configuration_getter import ConfigurationGetter
from ..cameras.images import Image


class DummyCameraThread(PictureThread):
    def __init__(
        self, config_getter: ConfigurationGetter, ntfy: typing.Optional[bool] = True
    ):
        super().__init__("dummy_camera", config_getter, ntfy=ntfy)

    @classmethod
    def get_camera(cls, config: typing.Mapping[str, typing.Any]) -> DummyCamera:
        kwargs  = {}
        if "width" in config:
            kwargs["width"] = config["width"]
        if "height" in config:
            kwargs["height"] = config["height"]
        return DummyCamera(**kwargs)

    @classmethod
    def check_config(cls, config_getter: ConfigurationGetter) -> typing.Optional[str]:
        cls._check_config(config_getter, "DummyCameraThread")
        return None
