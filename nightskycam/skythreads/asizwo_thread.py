import cv2
import typing
import nptyping as npt
import camera_zwo_asi
from PIL import Image as PILImage
from pathlib import Path
from .picture_thread import PictureThread, Camera, Image
from ..configuration_getter import ConfigurationGetter


class AsiImage(Image):
    def __init__(self, data: npt.NDArray) -> None:
        self._data = data

    def save(self, filepath: typing.Union[Path, str]) -> None:
        if isinstance(filepath, str):
            filepath = Path(filepath)
        folder = filepath.parent
        if not folder.exists():
            raise FileNotFoundError(
                f"fails to save image to {folder}: " "folder not found"
            )
        cv2.imwrite(str(filepath), self._data)
        # image = PILImage.fromarray(self._data)
        # image.save(filepath)

    def display(self, label: str = "nightskycam") -> None:
        cv2.imshow(label, self._data)
        cv2.waitKey(0)
        cv2.destroyAllWindows()

    def get_data(self) -> npt.NDArray:
        return self._data

    def set_data(self, data: npt.NDArray) -> None:
        self._data = data


class AsiZwoCamera(camera_zwo_asi.Camera, Camera):
    def __init__(self, index: int):
        super().__init__(index)

    def configure(self, config: typing.Mapping[str, typing.Any]) -> None:
        self.configure_from_toml(config)

    def picture(self) -> typing.Tuple[Image, str]:
        nimage = self.capture()
        meta = self.to_toml(specify_auto=False, non_writable=True)
        image = AsiImage(nimage.get_image())
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
    def get_camera(cls, config: typing.Mapping[str, typing.Any]) -> AsiZwoCamera:
        camera = AsiZwoCamera(0)
        camera.configure(config)
        return camera
        
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
