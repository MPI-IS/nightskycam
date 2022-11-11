import numpy as np
import typing
import time
import shutil
import datetime
import logging
from pathlib import Path
import nptyping as npt
from ..configuration_getter import ConfigurationGetter
from ..types import Configuration
from ..skythread import SkyThread
from ..metadata import Meta
from ..utils import postprocess
from ..cameras import images, camera

_logger = logging.getLogger("picture")


def _read_time(date_str: str) -> datetime.time:
    """
    Method that read time from a string and return a datetime object.
    Expected format is: HH:MM
    """
    return datetime.datetime.strptime(date_str, "%H:%M").time()


def _is_active(
    start_record: typing.Optional[datetime.time],
    end_record: typing.Optional[datetime.time],
    now: datetime.time,
) -> bool:
    if start_record is None:
        return True
    if end_record is None:
        return True
    time_now = datetime.time(hour=now.hour, minute=now.minute)
    if end_record < start_record:
        # end record: next day
        if time_now > start_record or time_now < end_record:
            return True
    else:
        # end record: same day
        if time_now > start_record and time_now < end_record:
            return True
    return False


def _next_picture_time(every: int):
    def _get_midnight():
        now = datetime.datetime.now()
        now_t = time.time()
        midnight = datetime.datetime(now.year, now.month, now.day, 0, 0, 0)
        delta = (now - midnight).seconds + ((now - midnight).microseconds) * 1e-6
        return now_t - delta

    now = time.time()
    midnight = _get_midnight()
    x = int((now - midnight) / every)
    return midnight + (x + 1) * every


class PictureThreadConfiguration:

    __slots__ = (
        "final_dir",
        "target_dir",
        "picture_every",
        "start_record",
        "end_record",
    )

    def __init__(self):
        self.final_dir: Path = Path("/tmp")
        self.target_dir: Path = Path("/tmp")
        self.picture_every: int = -1
        self.start_record: datetime.time = datetime.time(hour=0, minute=0)
        self.end_record: datetime.time = datetime.time(hour=0, minute=0)
        self.postprocess: typing.Dict[str, typing.Any] = {}
        self.file_format: str = "tiff"

    @classmethod
    def from_dict(cls, config: Configuration) -> object:

        instance = cls()

        for field in cls.__slots__:
            if field not in config.keys():
                raise KeyError(
                    f"Configuration for the picture thread misses "
                    f"the key: '{field}'"
                )
            else:
                setattr(instance, field, config[field])

        try:
            instance.picture_every = int(instance.picture_every)
        except Exception as e:
            raise Exception(
                f"failed to cast the configuration value 'picture_every' "
                f"({instance.picture_every}) to an int: {e}"
            )

        paths = ("final_dir", "target_dir")
        for path in paths:
            value_ = getattr(instance, path)
            value = Path(value_)
            if not value.is_dir():
                raise FileNotFoundError(f"failed to find the directory 'path' {value} ")
            else:
                setattr(instance, path, value)

        time_records = ("start_record", "end_record")
        tr_values = [getattr(instance, tr) for tr in time_records]
        if any([v == "None" for v in tr_values]):
            for tr in time_records:
                setattr(instance, tr, None)
        else:
            for tr in time_records:
                setattr(instance, tr, _read_time(getattr(instance, tr)))

        return instance


class PictureThread(SkyThread):
    def __init__(
        self,
        name: str,
        config_getter: ConfigurationGetter,
        ntfy: typing.Optional[bool] = True,
    ) -> None:
        super().__init__(config_getter, name, tags=["camera_flash"], ntfy=ntfy)
        full_class_name = str(type(self))
        if full_class_name.endswith("'>"):
            full_class_name = full_class_name[:-2]
        try:
            last_point = full_class_name.rindex(".")
        except ValueError:
            self._class_name = full_class_name
        else:
            self._class_name = full_class_name[last_point + 1 :]
        self._nb_pictures = 0
        self._camera: typing.Optional[camera.Camera] = None

    @classmethod
    def get_camera(
        cls,
        config: typing.Mapping[str, typing.Any],
    ) -> camera.Camera:
        raise NotImplementedError()

    @classmethod
    def _check_config(
        cls, config_getter: ConfigurationGetter, class_name: str
    ) -> typing.Optional[str]:
        config = config_getter.get(class_name)
        PictureThreadConfiguration.from_dict(config)
        return None

    def deploy_test(self) -> None:

        gnrl_config = self._config_getter.get(self._class_name)
        config = typing.cast(
            PictureThreadConfiguration,
            PictureThreadConfiguration.from_dict(gnrl_config),
        )

        camera = self.get_camera(gnrl_config)
        camera.active_configure(gnrl_config)
        camera.upon_active(gnrl_config)

        for filename in [f"deploy_test_{index}" for index in range(3)]:

            image: images.Image = camera.picture()
            image.filename = filename
            image.save(config.target_dir, fileformat="npy")

            target_file = config.target_dir / f"{filename}.npy"
            if not target_file.is_file():
                raise FileNotFoundError(
                    "a picture taken by the camera should have been saved "
                    f"in the file {target_file}. But this file could not be found."
                )
            else:
                target_file.unlink()

    def _step_active(
        self,
        config: PictureThreadConfiguration,
        destination_folder: typing.Optional[Path] = None,
    ) -> None:

        if self._camera is None:
            return None

        if config.end_record:
            self._status.set_misc("mode", f"active, will stop at {config.end_record}")
        else:
            self._status.set_misc("mode", "active (always)")

        # getting filename and general meta data
        _logger.debug("getting metadata")
        filename, gnrl_metadata = Meta.get()

        # taking the picture and related meta data
        _logger.info(f"taking picture {filename}")
        image: images.Image = self._camera.picture()
        image.filename = filename
        image.add_meta("general", gnrl_metadata)
        _logger.debug(f"saving {filename} to {config.final_dir}")
        image.save(
            config.final_dir,
            fileformat="npy",
        )

        self._nb_pictures += 1
        self._status.set_misc("number pictures taken", str(self._nb_pictures))

    def _step_inactive(self, config: PictureThreadConfiguration):
        if self._camera is None:
            return
        _logger.debug("not active time, skipping")
        self._status.set_misc(
            "mode", f"not active, should start at {config.start_record}"
        )

    def get_configuration(self) -> PictureThreadConfiguration:
        gnrl_config = self._config_getter.get(self._class_name)
        config = typing.cast(
            PictureThreadConfiguration,
            PictureThreadConfiguration.from_dict(gnrl_config),
        )
        return config

    def _sleep(self, config: PictureThreadConfiguration) -> None:
        while True:
            now = time.time()
            next_time = _next_picture_time(int(config.picture_every))
            sleep_time = max(0, next_time - now)
            _logger.debug(f"sleeping for {sleep_time} seconds")
            interrupted = self.sleep(sleep_time, interrupt_on_config_change=True)
            if not interrupted:
                break

    def _execute(self):

        # reading the current configuration
        _logger.debug("reading configuration")
        gnrl_config = self._config_getter.get(self._class_name)

        config = typing.cast(
            PictureThreadConfiguration,
            PictureThreadConfiguration.from_dict(gnrl_config),
        )

        active = _is_active(
            config.start_record, config.end_record, datetime.datetime.now().time()
        )

        if self._camera is None:
            _logger.debug("getting camera")
            self._camera = self.get_camera(gnrl_config)

        # pictures are taken only during "active time" (most likely: the night)
        if active:
            self._camera.active_configure(gnrl_config)
            self._camera.upon_active(gnrl_config)
            self._step_active(config)
        else:
            self._camera.inactive_configure(gnrl_config)
            self._camera.upon_inactive(gnrl_config)
            self._step_inactive(config)

        # getting info specific to this camera type
        for name, value in self._camera.get_misc().items():
            self._status.set_misc(name, value)

        # sleeping until next picture due
        self._sleep(config)
