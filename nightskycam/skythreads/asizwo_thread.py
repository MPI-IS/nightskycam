import typing
import camera_zwo_asi
from .picture_thread import PictureThread, Camera, Image
from ..configuration_getter import ConfigurationGetter


class AsiImage(Image, camera_zwo_asi.Image):
    def __init__(
        self, image_type: camera_zwo_asi.ImageType, width: int, height: int
    ) -> None:
        super(Image, self).__init__()
        super(camera_zwo_asi.Image, self).__init__(image_type, width, height)


class AsiZwoCamera(camera_zwo_asi.Camera, Camera):
    def __init__(self, index: int):
        super().__init__(index)

    @classmethod
    def from_dict(cls, path: typing.Mapping[str, typing.Any]) -> object:
        instance = cls(0)
        instance.configure_from_toml(path)
        return instance

    def picture(self) -> typing.Tuple[Image, str]:
        image = self.capture()
        meta = self.to_toml()
        return image, meta

    def get_misc(self) -> typing.Dict[str, str]:
        controls = self.get_controls()
        return {
            "temperature": controls["Temperature"].value,
            "cooler on": controls["CoolerOn"].value,
        }


class AsiZwoThread(PictureThread):
    def __init__(
        self, config_getter: ConfigurationGetter, ntfy: typing.Optional[bool] = True
    ):
        super().__init__("asi_zwo", config_getter, ntfy=ntfy)

    @classmethod
    def get_camera(
        cls, config: typing.Mapping[str, typing.Any], active: bool
    ) -> AsiZwoCamera:
        if not active:
            config["controllables"]["CoolerOn"] = 0
        return typing.cast(AsiZwoCamera, AsiZwoCamera.from_dict(config))

    @classmethod
    def check_config(cls, config_getter: ConfigurationGetter) -> typing.Optional[str]:

        cls._check_config(config_getter, "AsiZwoThread")

        config = config_getter.get("AsiZwoThread")
        try:
            AsiZwoCamera.from_dict(config)
        except Exception as e:
            return f"error with AsiZwoThread configuration: {e}"

        return None
