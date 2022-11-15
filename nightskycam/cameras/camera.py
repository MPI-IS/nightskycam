import typing
from . import images


class Camera(object):
    def picture(self) -> images.Image:
        raise NotImplementedError()

    def get_misc(self) -> typing.Dict[str, str]:
        d: typing.Dict[str, str] = {}
        return d

    def connected(self) -> bool:
        raise NotImplementedError()

    def active_configure(self, config: typing.Mapping[str, typing.Any]) -> None:
        raise NotImplementedError()

    def inactive_configure(self, config: typing.Mapping[str, typing.Any]) -> None:
        raise NotImplementedError()

    def upon_active(self, config: typing.Dict[str, typing.Any]) -> None:
        pass

    def upon_inactive(self, config: typing.Dict[str, typing.Any]) -> None:
        pass
