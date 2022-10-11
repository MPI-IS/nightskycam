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

_logger = logging.getLogger("picture")


class Image:
    def __init__(self) -> None:
        pass

    def save(self, path: Path) -> None:
        raise NotImplementedError()

    def display(self, label: str = "") -> None:
        raise NotImplementedError()

    def get_data(self) -> npt.NDArray:
        raise NotImplementedError()

    def set_data(self, image: npt.NDArray) -> None:
        raise NotImplementedError()


class DummyImage(Image):
    def save(self, path: Path) -> None:
        with open(path, "w+") as f:
            f.write("dummy image")

    def display(cls, label: str = "") -> None:
        print("pretend display of dummy image")

    def get_data(self) -> npt.NDArray:
        return np.array([0])

    def set_data(self, image: npt.NDArray) -> None:
        pass


class Camera(object):
    def picture(self) -> typing.Tuple[Image, str]:
        raise NotImplementedError()

    def get_misc(self) -> typing.Dict[str, str]:
        d: typing.Dict[str, str] = {}
        return d

    def active_configure(self, config: typing.Mapping[str, typing.Any]) -> None:
        raise NotImplementedError

    def inactive_configure(self, config: typing.Mapping[str, typing.Any]) -> None:
        raise NotImplementedError

    def upon_active(self, config: typing.Dict[str, typing.Any]) -> None:
        pass

    def upon_inactive(self, config: typing.Dict[str, typing.Any]) -> None:
        pass


class DummyCamera(Camera):
    def __init__(self) -> None:
        super().__init__()

    def picture(self) -> typing.Tuple[Image, str]:
        return DummyImage(), "dummy_image"

    def active_configure(self, config: typing.Mapping[str, typing.Any]) -> None:
        return

    def inactive_configure(self, config: typing.Mapping[str, typing.Any]) -> None:
        return


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


def _take_picture(camera) -> typing.Optional[typing.Tuple[Image, str]]:
    image, metadata = camera.picture()
    return image, metadata


def _save(data: typing.Union[Image, str], path: Path) -> None:
    if isinstance(data, str):
        with open(path, "w+") as f:
            f.write(data)
    else:
        data.save(path)


def _save_data(
    tmp_dir: Path,
    final_dir: Path,
    latest_dir: Path,
    image: Image,
    metadata: str,
    filename: str,
    file_format: str,
) -> None:

    # making sure the required folders exist
    for folder in (tmp_dir, final_dir, latest_dir):
        folder.mkdir(parents=True, exist_ok=True)

    # saving the image in tmp_dir, then copy it to
    # final_dir and latest_dir.
    image_tmp_path = tmp_dir / f"{filename}.{file_format}"
    image_final_path = final_dir / f"{filename}.{file_format}"
    image_latest_path = latest_dir / f"latest.{file_format}"
    metadata_tmp_path = tmp_dir / f"{filename}.toml"
    metadata_final_path = final_dir / f"{filename}.toml"
    metadata_latest_path = latest_dir / "latest.txt"
    _save(image, image_tmp_path)
    _save(metadata, metadata_tmp_path)
    shutil.copy(image_tmp_path, image_latest_path)
    shutil.copy(metadata_tmp_path, metadata_latest_path)
    image_tmp_path.rename(image_final_path)
    metadata_tmp_path.rename(metadata_final_path)


class PictureThreadConfiguration:

    __slots__ = (
        "tmp_dir",
        "final_dir",
        "latest_dir",
        "picture_every",
        "start_record",
        "end_record",
        "postprocess",
        "file_format",
    )

    def __init__(self):
        self.tmp_dir: Path = Path("/tmp")
        self.final_dir: Path = Path("/tmp")
        self.latest_dir: Path = Path("/tmp")
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

        paths = ("tmp_dir", "final_dir", "latest_dir")
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

        if "postprocess" in config:
            instance.postprocess = config["postprocess"]

        instance.file_format = str(config["file_format"])

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
        self._camera: typing.Optional[Camera] = None

    @classmethod
    def get_camera(
        cls,
        config: typing.Mapping[str, typing.Any],
    ) -> Camera:
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

        filenames = [f"deploy_test_{index}" for index in range(3)]
        metadatas = [
            f"deploy test metadata for file {filename}" for filename in filenames
        ]

        for filename, metadata in zip(filenames, metadatas):

            image, image_metadata = camera.picture()

            if config.postprocess:
                np_image = image.get_data()
                np_image, postprocess_metadata = postprocess.apply(
                    np_image, config.postprocess, dry_run=False
                )
                image.set_data(np_image)

            _save_data(
                config.tmp_dir,
                config.final_dir,
                config.latest_dir,
                image,
                metadata + "\n" + image_metadata + "\n" + postprocess_metadata,
                filename,
                config.file_format,
            )

    def _step_active(self, config: PictureThreadConfiguration) -> None:

        if self._camera is None:
            return

        if config.end_record:
            self._status.set_misc("mode", f"active, will stop at {config.end_record}")
        else:
            self._status.set_misc("mode", "active (always)")

        # getting filename and general meta data
        _logger.debug("getting metadata")
        filename, gnrl_metadata = Meta.get()

        _logger.info(f"taking and saving picture {filename}")

        # taking the picture and related meta data
        if self._camera is not None:
            _logger.debug("taking picture")
            image, image_metadata = self._camera.picture()

        # postprocess
        if config.postprocess:
            np_image = image.get_data()
            np_image, postprocess_metadata = postprocess.apply(
                np_image, config.postprocess, dry_run=False
            )
            image.set_data(np_image)
        else:
            _logger.info("no 'postprocess' key in the configuration, skipping")
            postprocess_metadata = ""

        # complete meta data
        metadata = f"{gnrl_metadata}\n{image_metadata}\n{postprocess_metadata}"

        # saving the image and related metadata
        _logger.debug(f"saving {filename}")
        _save_data(
            config.tmp_dir,
            config.final_dir,
            config.latest_dir,
            image,
            metadata,
            filename,
            config.file_format,
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

        # adding postprocess info
        if config.postprocess:
            self._status.set_misc(
                "image postprocess",
                ", ".join([str(pp) for pp in config.postprocess["order"]]),
            )

        # sleeping a bit
        now = time.time()
        next_time = _next_picture_time(int(config.picture_every))
        sleep_time = max(0, next_time - now)
        _logger.debug(f"sleeping for {sleep_time} seconds")
        self.sleep(sleep_time)
