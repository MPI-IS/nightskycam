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

    def configure(self, config: typing.Mapping[str, typing.Any]) -> None:
        self.configure_from_toml(config)

    def picture(self) -> typing.Tuple[Image, str]:
        image = self.capture()
        meta = self.to_toml(specify_auto=False)
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
    def get_camera(cls) -> AsiZwoCamera:
        return AsiZwoCamera(0)

    @classmethod
    def check_config(cls, config_getter: ConfigurationGetter) -> typing.Optional[str]:

        cls._check_config(config_getter, "AsiZwoThread")

        config = config_getter.get("AsiZwoThread")
        try:
            cam = AsiZwoCamera(0)
            cam.configure(config)
        except Exception as e:
            return f"error with AsiZwoThread configuration: {e}"

        return None

    def _update_config_for_inactive(
        self, config: typing.Dict[str, typing.Any]
    ) -> typing.Dict[str, typing.Any]:
        config["controllables"]["CoolerOn"] = 0
        return config
