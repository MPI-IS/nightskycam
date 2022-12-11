import typing
from ..skythread import SkyThread
from ..types import GlobalConfiguration
from ..configuration_file import get_skythreads
from .camera import Camera
from .dummy_camera import DummyCamera
from .asizwo_camera import AsiZwoCamera


def get_camera(config: GlobalConfiguration, **kwargs) -> Camera:

    skythreads: typing.List[typing.Type[SkyThread]] = get_skythreads(config)

    for skythread in skythreads:

        if "AsiZwoThread" in skythread.__name__:
            return AsiZwoCamera(**kwargs)

        elif "DummyCameraThread" in skythread.__name__:
            return DummyCamera(**kwargs)

    picture_threads = "AsiZwoThread, DummyCameraThread"
    raise NotImplementedError(
        "Failed to find a picture thread in the configuration file. "
        f"Known: {picture_threads}"
    )
