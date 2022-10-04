import typing
import time
import shutil
import datetime
import logging
from pathlib import Path
from ..configuration_getter import ConfigurationGetter
from ..types import Configuration
from ..skythread import SkyThread
from ..metadata import Meta

_logger = logging.getLogger("picture")


class Image:
    def save(self, path: Path) -> None:
        raise NotImplementedError()

    def display(self, label: str = "") -> None:
        raise NotImplementedError()


class DummyImage(Image):
    def save(self, path: Path) -> None:
        with open(path, "w+") as f:
            f.write("dummy image")

    def display(cls, label: str = "") -> None:
        print("pretend display of dummy image")


class Camera(object):
    def picture(self) -> typing.Tuple[Image, str]:
        raise NotImplementedError()

    def configure(self, config: typing.Dict[str, typing.Any]) -> None:
        raise NotImplementedError()

    def get_misc(self) -> typing.Dict[str, str]:
        d: typing.Dict[str, str] = {}
        return d


class DummyCamera(Camera):
    def __init__(self) -> None:
        super().__init__()

    def picture(self) -> typing.Tuple[Image, str]:
        return DummyImage(), "dummy_image"

    def configure(self, config: typing.Dict[str, typing.Any]) -> None:
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
    if time_now > start_record or time_now < end_record:
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
) -> None:

    # making sure the required folders exist
    for folder in (tmp_dir, final_dir, latest_dir):
        folder.mkdir(parents=True, exist_ok=True)

    # saving the image in tmp_dir, then copy it to
    # final_dir and latest_dir.
    image_tmp_path = tmp_dir / f"{filename}.tiff"
    image_final_path = final_dir / f"{filename}.tiff"
    image_latest_path = latest_dir / "latest.tiff"
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
    )

    def __init__(self):
        self.tmp_dir: Path = Path("/tmp")
        self.final_dir: Path = Path("/tmp")
        self.latest_dir: Path = Path("/tmp")
        self.picture_every: int = -1
        self.start_record: datetime.time = datetime.time(hour=0, minute=0)
        self.end_record: datetime.time = datetime.time(hour=0, minute=0)

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
    def get_camera(cls) -> Camera:
        raise NotImplementedError()

    @classmethod
    def _check_config(
        cls, config_getter: ConfigurationGetter, class_name: str
    ) -> typing.Optional[str]:

        config = config_getter.get(class_name)

        other_keys = ("tmp_dir", "final_dir", "latest_dir")
        for ok in other_keys:
            if ok not in config.keys():
                raise KeyError(f"Config error for {class_name}, missing key: '{ok}'")
            path = Path(config[ok])
            try:
                path.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                raise Exception(
                    f"Config error for {class_name}, failed to create the {ok} directory {config[ok]}: {e}"
                )
        if "picture_every" not in config:
            raise KeyError(
                "Config error for {class_name}, missing key: 'picture_every'"
            )
        try:
            int(config["picture_every"])
        except Exception:
            value = config["picture_every"]
            raise ValueError(
                f"Config error for {class_name}, failed to cast 'picture_every' "
                f"to in int (value: {value})"
            )

        datetime_keys = ("start_record", "end_record")
        for dk in datetime_keys:
            if dk not in config.keys():
                raise KeyError(f"Config error for {class_name}, missing key: '{dk}'")
            if config[dk] != "None":
                try:
                    _read_time(config[dk])
                except Exception as e:
                    raise ValueError(
                        f"Config error for {class_name}, failed to parse the value "
                        f"'{config[dk]}', expected format: 'hour:minute': {e}"
                    )

        return None

    def deploy_test(self) -> None:

        gnrl_config = self._config_getter.get(self._class_name)
        config = typing.cast(
            PictureThreadConfiguration,
            PictureThreadConfiguration.from_dict(gnrl_config),
        )

        camera = self.get_camera()

        filenames = [f"deploy_test_{index}" for index in range(3)]
        metadatas = [
            f"deploy test metadata for file {filename}" for filename in filenames
        ]

        for filename, metadata in zip(filenames, metadatas):

            image, image_metadata = camera.picture()

            _save_data(
                config.tmp_dir,
                config.final_dir,
                config.latest_dir,
                image,
                metadata + "\n" + image_metadata,
                filename,
            )

    def _update_config_for_inactive(
        self, config: typing.Dict[str, typing.Any]
    ) -> typing.Dict[str, typing.Any]:
        return config

    def _step_active(self, config: PictureThreadConfiguration) -> None:

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

        # complete meta data
        metadata = f"{gnrl_metadata}\n{image_metadata}"

        # saving the image and related metadata
        _logger.debug(f"saving {filename}")
        _save_data(
            config.tmp_dir,
            config.final_dir,
            config.latest_dir,
            image,
            metadata,
            filename,
        )

        self._nb_pictures += 1
        self._status.set_misc("number pictures taken", str(self._nb_pictures))

    def _step_inactive(self, config: PictureThreadConfiguration):

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
            self._camera = self.get_camera()

        # pictures are taken only during "active time" (most likely: the night)
        try:
            if active:
                self._camera.configure(gnrl_config)
                self._step_active(config)

            else:
                gnrl_config = self._update_config_for_inactive(gnrl_config)
                self._camera.configure(gnrl_config)
                self._step_inactive(config)
        except Exception as e:
            self._camera = None
            raise e

        # getting info specific to this camera type
        for name, value in self._camera.get_misc().items():
            self._status.set_misc(name, value)

        # sleeping a bit
        now = time.time()
        next_time = _next_picture_time(int(config.picture_every))
        sleep_time = max(0, next_time - now)
        _logger.debug(f"sleeping for {sleep_time} seconds")
        self.sleep(sleep_time)
