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
from ..utils import images

_logger = logging.getLogger("picture")

MetaData = typing.Mapping[str,typing.Any]

class Image:

    __slots__ = (
        "filename", "current_dir", "fileformat",
        "data", "metadata", "cv2_all_formats"
    )

    def __init__(self, data: npt.ArrayList, metadata: Metadata)->None:
        self.filename: typing.Optional[str] = None
        self.current_dir: typing.Optional[Path] = None
        self.fileformat: typing.Optional[str] = None
        self.data: np.ArrayLike = data
        self.metadata: Metadata = metadata
        

    def save(
            target_dir: Path,
            filename: typing.Optional[str] = None,
            fileformat: str = "npy",
            cv2_all_formats: CV2AllFormats = {}
    )->None:

        if not target_dir.is_dir():
            raise FileNotFoundError(
                f"can not save image in {target_dir}: "
                "directory not found"
            )

        if filename is None and self.filename is None:
            raise ValueError(
                f"can not save image to {target_dir}: "
                "filename is not specified"
            )

        if filename is not None:
            self.filename = filename

        self.fileformat = fileformat

        data_file = target_dir / f"{self.filename}.{self.fileformat}"
        metadata_file = target_dir / f"{self.filename}.toml"
        
        if self.fileformat == "npy":
            np.save(data_file, self.data)
        else:
            images.save(data_file, self.data, cv2_all_formats)

        with open(metadata_file,"w") as f:
            toml.dump(self.metadata,f)
        
        
    def move(self, destination_dir: Path)->None:

        for attr in self.__slots__:
            if getattr(self,attr) is None:
                raise ValueError(
                    f"failed to move image to {destination_dir}: "
                    f"attribute {attr} is None"
                )

        if not destination_dir.is_dir():
            raise FileNotFoundError(
                f"can not move image {self.filename} to {destination_dir}: "
                "directory not found"
            )
        
        data_file = self.current_dir / f"{self.filename}.{self.fileformat}"
        meta_file = self.current_dir / f"{self.filename}.toml"

        if not data_file.is_file():
            raise FileNotFoundError(
                f"can not move image f{data_file} to {destination_dir}: "
                "file not found"
            )

        if not meta_file.is_file():
            raise FileNotFoundError(
                f"can not move image f{meta_file} to {destination_dir}: "
                "file not found"
            )

        dest_data_file = destination_dir / f"{self.filename}.{self.fileformat}"
        dest_meta_file = destination_dir / f"{self.filename}.toml"
        
        data_file.rename(dest_data_file)
        meta_file.rename(dest_meta_file)

        

class Camera(object):
    def picture(self) -> typing.Tuple[npt.ArrayLike, Metadata]:
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


class DummyCamera(Camera):
    def __init__(self) -> None:
        super().__init__()

    def connected(self) -> bool:
        return True

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


def _save(data: typing.Union[Image, str], path: Path, cv2_all_formats: images.CV2AllFormats) -> None:
    if isinstance(data, str):
        with open(path, "w+") as f:
            f.write(data)
    else:
        data.save(path, cv2_all_formats)


def _save_data(
    tmp_dir: Path,
    final_dir: Path,
    latest_dir: typing.Optional[Path],
    image: Image,
    metadata: str,
    filename: str,
    file_format: str,
    cv2_all_formats: images.CV2AllFormats
) -> typing.Tuple[Path, Path]:

    # making sure the required folders exist
    for folder in (tmp_dir, final_dir):
        folder.mkdir(parents=True, exist_ok=True)
    if latest_dir:
        latest_dir.mkdir(parents=True, exist_ok=True)

    # saving the image in tmp_dir, then copy it to
    # final_dir and latest_dir.
    image_tmp_path = tmp_dir / f"{filename}.{file_format}"
    image_final_path = final_dir / f"{filename}.{file_format}"
    if latest_dir:
        image_latest_path = latest_dir / f"latest.{file_format}"
    metadata_tmp_path = tmp_dir / f"{filename}.toml"
    metadata_final_path = final_dir / f"{filename}.toml"
    if latest_dir:
        metadata_latest_path = latest_dir / "latest.txt"
    _save(image, image_tmp_path, cv2_all_formats)
    _save(metadata, metadata_tmp_path, cv2_all_formats)
    if latest_dir:
        shutil.copy(image_tmp_path, image_latest_path)
        shutil.copy(metadata_tmp_path, metadata_latest_path)
    image_tmp_path.rename(image_final_path)
    metadata_tmp_path.rename(metadata_final_path)
    return image_final_path, metadata_final_path


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
                gnrl_config["fileformat"]
            )

    def _step_active(
        self,
        config: PictureThreadConfiguration,
        destination_folder: typing.Optional[Path] = None,
    ) -> typing.Optional[typing.Tuple[Path, Path]]:

        if self._camera is None:
            return None

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
        if destination_folder is None:
            _logger.debug(f"saving {filename}")
            image_path, meta_path = _save_data(
                config.tmp_dir,
                config.final_dir,
                config.latest_dir,
                image,
                metadata,
                filename,
                config.file_format,
                gnrl_config["fileformat"]
            )
        else:
            _logger.debug(f"saving {filename} to {destination_folder}")
            if not destination_folder.is_dir():
                raise FileNotFoundError(
                    f"can not save image in {destination_folder}: folder not found"
                )
            image_path, meta_path = _save_data(
                destination_folder,
                destination_folder,
                None,
                image,
                metadata,
                filename,
                config.file_format,
                gnrl_config["fileformat"]
            )

        self._nb_pictures += 1
        self._status.set_misc("number pictures taken", str(self._nb_pictures))
        return image_path, meta_path

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
