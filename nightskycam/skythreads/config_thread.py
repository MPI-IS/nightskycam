import toml
import typing
import tempfile
import logging
from pathlib import Path
from ..skythread import SkyThread
from .. import configuration_file as cf
from ..locks import Locks
from ..types import Configuration
from ..configuration_getter import ConfigurationGetter
from ..utils import ntfy

_logger = logging.getLogger("config")


def download_remote_if_better(
    url: str,
    target_folder: Path,
    tmp_folder: typing.Optional[Path] = None,
    main_file: str = "nightskycam_config.toml",
) -> typing.Optional[Path]:

    # checking what's the "best" remote file
    _logger.debug(f"list configuration files at {url}")
    remote_files = cf.list_remote_config_files(url)

    # no config files found remotely, exit
    if not remote_files:
        return None

    best_remote_file = cf.best_config_file(remote_files)
    remote_version = cf.get_version_number(best_remote_file)

    # checking what the "best" local file
    local_files = cf.list_local_config_files(target_folder)
    if local_files:
        best_local_file = cf.best_config_file(local_files)
        local_version = cf.get_version_number(best_local_file)
        # best local file: better than the remote file,
        # so cleaning and exit
        if local_version >= remote_version:
            return None

    # remote is better, so getting it
    _logger.info(f"found a new configuration file at {url}, updating")
    cf.download_file(url, best_remote_file, target_folder, tmp_folder)
    return target_folder / best_remote_file


def upgrade_config_file(
    url: str,
    target_folder: Path,
    tmp_folder: typing.Optional[Path] = None,
    main_file: str = "nightskycam_config.toml",
) -> None:

    # checking what's the "best" remote file
    _logger.debug(f"list configuration files at {url}")
    remote_files = cf.list_remote_config_files(url)

    # no config files found remotely, exit
    if not remote_files:
        return

    best_remote_file = cf.best_config_file(remote_files)
    remote_version = cf.get_version_number(best_remote_file)

    # checking what the "best" local file
    local_files = cf.list_local_config_files(target_folder)
    if local_files:
        best_local_file = cf.best_config_file(local_files)
        local_version = cf.get_version_number(best_local_file)
        # best local file: better than the remote file,
        # so cleaning and exit
        if local_version >= remote_version:
            cf.local_config_cleanup(target_folder, main_file)
            return

    # remote is better, so getting it
    _logger.info(f"found a new configuration file at {url}, updating")
    cf.download_file(url, best_remote_file, target_folder, tmp_folder)
    cf.local_config_cleanup(target_folder, main_file)
    return


class ConfigThreadConfiguration:
    """
    Container for the configuration values required to
    run a ConfigThread.

    Attributes:
      url: Remote location from where a newer configuration file may
        be downloaded.
      update_every: The period (in seconds) at which the configuration thread
        will check if a newer configuration file is available.
    """

    __slots__ = ("url", "update_every")

    def __init__(self, url: str = "undefined", update_every: int = -1):
        self.url: str = url
        self.update_every: float = update_every

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

        instance.url = str(instance.url)

        try:
            instance.update_every = float(instance.update_every)
        except Exception as e:
            raise Exception(
                f"failed to cast the configuration value 'update_every' "
                f"({instance.update_every}) to an float: {e}"
            )

        return instance


class ConfigThread(SkyThread):
    def __init__(self, config_getter: ConfigurationGetter):
        super().__init__(config_getter, "configuration", tags=["inbox_tray"])

    @classmethod
    def check_config(cls, config_getter: ConfigurationGetter) -> typing.Optional[str]:
        config = config_getter.get("ConfigThread")
        try:
            ConfigThreadConfiguration.from_dict(config)
        except Exception as e:
            return str(e)

        return None

    def deploy_test(self) -> None:

        # reading the configuration
        config_ = self._config_getter.get("ConfigThread")
        config = typing.cast(
            ConfigThreadConfiguration, ConfigThreadConfiguration.from_dict(config_)
        )

        # listing the configuration files that can be found
        # at the url provided by the config
        remote_config_files = cf.list_remote_config_files(config.url)
        if not remote_config_files:
            raise ValueError(
                f"failed to find any suitable configuration file at {config.url}"
            )

        # the best of these configurations
        best_remote_file = cf.best_config_file(remote_config_files)

        # downloading it
        with tempfile.TemporaryDirectory() as local_tmp_dir_:

            local_tmp_dir = Path(local_tmp_dir_)
            cf.download_file(config.url, best_remote_file, local_tmp_dir)
            downloaded_file_ = local_tmp_dir / best_remote_file
            if not downloaded_file_.is_file():
                raise RuntimeError(
                    f"failed to download {best_remote_file} from {config.url}"
                )

            # checking it is at least a toml file
            try:
                content = toml.load(downloaded_file_)
            except Exception as e:
                raise Exception(
                    f"the remote configuration file ${best_remote_file} fails to be (toml) parsed: {e}"
                )

        # at least the 'main' key should be present
        try:
            content["main"]
        except KeyError:
            raise KeyError(
                f"the remote configuration file ${best_remote_file} does not have the required key 'main'"
            )

        # downloading newer configuration file, if any
        downloaded_file: typing.Optional[Path] = download_remote_if_better(
            config.url, cf.configuration_file_folder()
        )

        # a new file was downloaded
        if downloaded_file:
            try:
                # checking if any issue with it
                cf.is_a_valid_config_file(downloaded_file)
            except Exception as e:
                raise Exception(
                    f"the downloaded configuration file {downloaded_file.name} "
                    f"has issues and will not be used: {e}"
                )
            else:
                # the config file seems fine, replacing the current file
                with Locks.get_config_lock():
                    cf.local_config_cleanup(
                        downloaded_file.parent, "nightskycam_config.toml"
                    )

    def _execute(self):

        _logger.debug("reading configuration")
        config_ = self._config_getter.get("ConfigThread")
        config = typing.cast(
            ConfigThreadConfiguration, ConfigThreadConfiguration.from_dict(config_)
        )

        # downloading newer configuration file, if any
        downloaded_file: typing.Optional[Path] = download_remote_if_better(
            config.url, cf.configuration_file_folder()
        )

        # a new file was downloaded
        if downloaded_file:
            try:
                # checking if any issue with it
                cf.is_a_valid_config_file(downloaded_file)
            except Exception as e:
                # some issue with it, not using it !
                _logger.error(
                    f"the downloaded configuration file {downloaded_file.name} "
                    f"has issues and will not be used: {e}"
                )

            else:
                # the config file seems fine, replacing the current file
                _logger.debug(f"checking for newer configuration file at {config.url}")
                with Locks.get_config_lock():
                    cf.local_config_cleanup(
                        downloaded_file.parent, "nightskycam_config.toml"
                    )
                    _logger.info(f"now using configuration file {downloaded_file.name}")
                    ntfy.safe_publish(
                        self._config_getter,
                        3,
                        "new configuration file",
                        f"now using configuration file {downloaded_file.name}",
                        ["new"],
                    )
        # sleeping a bit
        _logger.debug(f"sleeping for {config.update_every}")
        self.sleep(config.update_every)
