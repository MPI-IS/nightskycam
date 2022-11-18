import logging
import typing
import cv2
import socket
import datetime
from pathlib import Path
from ..utils.ftp import get_ftp, FtpConfig
from ..types import Configuration
from ..configuration_getter import ConfigurationGetter
from ..skythread import SkyThread
from ..utils import folder_stats
import numpy as np

_logger = logging.getLogger("ftp")


def get_remote_dir() -> Path:
    """
    Returns nightskycam / hostname / current date /
    """
    hostname = socket.gethostname()
    date = datetime.datetime.now().strftime("%Y_%m_%d")
    return Path("nightskycam") / hostname / date


class FtpThreadConfiguration:
    def __init__(self):
        self.port: int = -1
        self.host: str = "undefined"
        self.upload_every: int = -1
        self.username: str = "Anomymous"
        self.passwd: str = "not entered"
        self.local_dir: Path = "undefined"
        self.batch: int = -1

    @classmethod
    def from_dict(cls, config: Configuration) -> object:
        instance = cls()
        mandatory = ("host", "upload_every", "batch")
        for m in mandatory:
            try:
                value = config[m]
            except KeyError:
                raise KeyError(
                    f"failed to find the mandatory key {m} "
                    f"in the configuration for FtpThread"
                )
        instance.host = str(config["host"])

        to_int = ("upload_every", "port", "batch")
        for field in to_int:
            try:
                value = config[field]
            except Exception:
                pass
            else:
                try:
                    int_value = int(value)
                except Exception as e:
                    raise ValueError(
                        f"configuration for FtpThread: "
                        f"failed to cast the value for '{field}' ({value}) "
                        f"to an int ({e})"
                    )
            setattr(instance, field, int_value)

        if "username" in config.keys():
            if "passwd" not in config.keys():
                raise ValueError(
                    "configuration for FtpThread has a configuration "
                    f"for 'username' ({config['username']}) but not for 'passwd'"
                )
            instance.username = config["username"]
            instance.passwd = config["passwd"]

        try:
            local_dir_ = config["local_dir"]
        except KeyError:
            pass
        else:
            local_dir = Path(str(local_dir_))
            try:
                local_dir.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                raise Exception(
                    f"configuration for FtpThread set {local_dir} as the "
                    "directory, but creation/access to this file failed with "
                    f"the error: {e}"
                )
            else:
                instance.local_dir = local_dir

        return instance

    def get_config(self) -> FtpConfig:
        return FtpConfig(self.username, self.passwd, self.host, self.port)


def _is_folder_empty(path: Path) -> bool:
    if not path.is_dir():
        raise FileNotFoundError(
            f"failed to check if folder {path} is empty: folder not found"
        )
    return not any(Path(path).iterdir())


def _upload_files(
    config: FtpConfig,
    local_dir: Path,
    remote_dir: Path,
    batch_size: int,
    glob: typing.Optional[str] = None,
) -> typing.Tuple[int, int]:
    if not local_dir.is_dir():
        raise FileNotFoundError(
            f"failing to upload the content of " f"{local_dir}: no such directory"
        )
    if not _is_folder_empty(local_dir):
        _logger.info(f"uploading some of the content of {local_dir}")
        with get_ftp(config, remote_dir) as ftp:
            return ftp.upload_dir(
                local_dir, delete_local=True, batch_size=batch_size, glob=glob
            )
    return 0, 0


class FtpThread(SkyThread):
    def __init__(self, config_getter: ConfigurationGetter):
        super().__init__(config_getter, "ftp", tags=["satellite"])
        self._nb_files = 0
        self._uploaded_size = 0

    @classmethod
    def check_config(cls, config_getter: ConfigurationGetter) -> typing.Optional[str]:
        """
        Returns None if the configuration is valid, a
        string describing why the configuration is invalid
        otherwise. See the documentation of FtpThreadConfiguration.from_dict.
        """
        config: Configuration = config_getter.get("FtpThread")
        try:
            FtpThreadConfiguration.from_dict(config)
        except Exception as e:
            return str(e)

        return None

    def deploy_test(self) -> None:

        # reading the configuration
        config_ = self._config_getter.get("FtpThread")
        config = typing.cast(
            FtpThreadConfiguration, FtpThreadConfiguration.from_dict(config_)
        )

        # deleting existing deploy test files
        glob = "deploy_test_*.*"
        deploy_files = config.local_dir.glob(glob)
        for deploy_file in deploy_files:
            deploy_file.unlink()

        # creating testing images that will be uploaded
        nb_images = 3
        height = 340
        width = 480
        image_names = [f"deploy_test_{index}.bmp" for index in range(nb_images)]
        images: typing.Dict[Path, np.typing.ArrayLike] = {
            Path(config.local_dir / name): np.ndarray((height, width), dtype=np.uint8)
            for name in image_names
        }
        for path, image in images.items():
            cv2.imwrite(str(path), image)

        # checking the testing images have been successfully written
        for path in images.keys():
            if not path.is_file():
                raise FileNotFoundError(f"could not find {path} right after writing it")

        # uploading the content of the local directory (i.e
        # the test images writen above)
        nb_uploaded = 0
        while nb_uploaded < nb_images:
            nb_files, _ = _upload_files(
                config.get_config(),
                config.local_dir,
                get_remote_dir(),
                config.batch,
                glob=glob,
            )
            nb_uploaded += nb_files

        # after upload, the local images should have been deleted locally
        for path in images.keys():
            if path.is_file():
                raise Exception(
                    f"{path} has been uploaded, and is expected to have been "
                    f"locally deleted, but is still present"
                )

        # double checking the files are on the ftp server
        with get_ftp(config.get_config(), get_remote_dir()) as ftp:

            remote_files = ftp.ls()
            for path in images.keys():
                filename = path.name
                if filename not in remote_files:
                    remote_dir = get_remote_dir()
                    raise Exception(
                        f"file {path} has been uploaded to {config.host}{remote_dir}, "
                        f"but could not be found there."
                    )

    def _execute(self):

        # reading the current configuration
        _logger.debug("reading configuration")
        config_ = self._config_getter.get("FtpThread")
        config = FtpThreadConfiguration.from_dict(config_)

        # uploading all files that are in the
        # local folder
        nb_files, uploaded_size = _upload_files(
            config.get_config(), config.local_dir, get_remote_dir(), config.batch
        )

        self._nb_files += nb_files
        self._uploaded_size += uploaded_size

        self._status.set_misc("uploaded files", str(self._nb_files))
        self._status.set_misc(
            "uploaded size", folder_stats.convert_size(self._uploaded_size)
        )

        remaining_files: typing.Dict[str, int] = folder_stats.list_nb_files(
            config.local_dir
        )
        remaining_files_str = ", ".join(
            [
                f"{extension}: {nb_files}"
                for extension, nb_files in remaining_files.items()
            ]
        )
        self._status.set_misc("remaining files to upload", remaining_files_str)
        self._status.set_misc(
            "remaining size to upload",
            folder_stats.convert_size(folder_stats.folder_size(config.local_dir)),
        )

        # sleeping a bit
        _logger.debug(f"sleeping {config.upload_every} seconds")
        self.sleep(config.upload_every)
