import numpy as Numpy
from .camera import Camera
from .. import images


class DummyCamera(Camera):
    def __init__(self) -> None:
        super().__init__()

    def connected(self) -> bool:
        return True

    def picture(self) -> images.Image:
        data = np.zeros((200, 100))
        return images.Image(data, {"type": "dummy_image"})

    def active_configure(self, config: typing.Mapping[str, typing.Any]) -> None:
        return

    def inactive_configure(self, config: typing.Mapping[str, typing.Any]) -> None:
        return
