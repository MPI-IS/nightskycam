import typing
from ..cameras.asizwo_camera import AsiZwoCamera
from .picture_thread import PictureThread
from ..configuration_getter import ConfigurationGetter


class AsiZwoThread(PictureThread):
    def __init__(self, config_getter: ConfigurationGetter):
        super().__init__("asi_zwo", config_getter)

    @classmethod
    def get_camera(cls, config: typing.Mapping[str, typing.Any]) -> AsiZwoCamera:
        camera = AsiZwoCamera(0)
        return camera

    @classmethod
    def check_config(cls, config_getter: ConfigurationGetter) -> typing.Optional[str]:
        cls._check_config(config_getter, "AsiZwoThread")
        return None
