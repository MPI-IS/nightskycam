import typing
import numpy as np
from .camera import Camera
from . import images


class DummyCamera(Camera):
    def __init__(self, width: int=200, height: int=100) -> None:
        super().__init__()
        self._width = width
        self._height = height

    def connected(self) -> bool:
        return True

    def picture(self) -> images.Image:
        data = np.zeros((self._width, self.height))
        return images.Image(data, {"type": "dummy_image"})

    def active_configure(self, config: typing.Mapping[str, typing.Any]) -> None:
        return

    def inactive_configure(self, config: typing.Mapping[str, typing.Any]) -> None:
        return
