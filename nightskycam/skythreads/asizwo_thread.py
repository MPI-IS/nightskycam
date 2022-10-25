import typing
import nptyping as npt
import camera_zwo_asi
from pathlib import Path
from .picture_thread import PictureThread, Camera, Image
from ..configuration_getter import ConfigurationGetter
from ..utils import images


class AsiImage(Image):
    def __init__(self, data: npt.NDArray) -> None:
        self._data = data

    def save(self, filepath: typing.Union[Path, str], cv2_all_formats = images.CV2AllFormats) -> None:
        if isinstance(filepath, str):
            filepath = Path(filepath)
        images.save(filepath, self._data, cv2_all_formats)

    def display(self, label: str = "nightskycam") -> None:
        images.display(label, self._data)

    def get_data(self) -> npt.NDArray:
        return self._data

    def set_data(self, data: npt.NDArray) -> None:
        self._data = data


class AsiZwoCamera(Camera):
    def __init__(self, index: int):
        self._index = index
        self._camera = camera_zwo_asi.Camera(index)

    def connected(self) -> bool:
        try:
            self._camera.get_controls()
        except Exception:
            return False
        return True

    def _configure(self, config: typing.Mapping[str, typing.Any]) -> None:
        self._camera.configure_from_toml(config)

    def active_configure(self, config: typing.Mapping[str, typing.Any]) -> None:
        self._configure(config)
        if config["controllables"]["CoolerOn"] > 0:
            self._camera.set_control("CoolerOn", 1)

    def inactive_configure(self, config: typing.Mapping[str, typing.Any]) -> None:
        config["controllables"]["CoolerOn"] = 0
        self._configure(config)
        self._camera.set_control("CoolerOn", 0)

    def picture(self) -> typing.Tuple[Image, str]:
        nimage = self._camera.capture()
        meta = self._camera.to_toml(specify_auto=False, non_writable=True)
        image = AsiImage(nimage.get_image())
        return image, meta

    def get_misc(self) -> typing.Dict[str, str]:
        controls = self._camera.get_controls()
        return {
            "temperature": controls["Temperature"].value / 10.0,
            "cooler on": controls["CoolerOn"].value,
        }

    def upon_inactive(self, config: typing.Dict[str, typing.Any]) -> None:
        return

    def upon_active(self, config: typing.Dict[str, typing.Any]) -> None:
        return


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
