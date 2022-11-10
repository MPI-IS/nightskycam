import typing
import nptyping as npt
import camera_zwo_asi
from pathlib import Path
from .picture_thread import PictureThread, Camera, Image
from ..configuration_getter import ConfigurationGetter
from ..utils import images


class AsiZwoThread(PictureThread):
    def __init__(
        self, config_getter: ConfigurationGetter, ntfy: typing.Optional[bool] = True
    ):
        super().__init__("asi_zwo", config_getter, ntfy=ntfy)

    @classmethod
    def get_camera(cls, config: typing.Mapping[str, typing.Any]) -> AsiZwoCamera:
        camera = AsiZwoCamera(0)
        return camera

    @classmethod
    def check_config(cls, config_getter: ConfigurationGetter) -> typing.Optional[str]:
        cls._check_config(config_getter, "AsiZwoThread")
        return None
