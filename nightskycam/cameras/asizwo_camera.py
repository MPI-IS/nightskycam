import camera_zwo_asi
import typing
from .camera import Camera
from . import images


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

    def picture(self) -> images.Image:
        nimage = self._camera.capture()
        meta = self._camera.to_dict(specify_auto=False, non_writable=True)
        return images.Image(nimage.get_data(), meta)

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
