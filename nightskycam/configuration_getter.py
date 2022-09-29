import os
import copy
import typing
import logging
import toml
from pathlib import Path
from jinja2 import Template
from .types import Configuration, GlobalConfiguration
from .locks import Locks

# from .utils import ntfy

_logger = logging.getLogger("configuration_getter")


_main_folder = Path("/opt/nightskycam")
_globals_file = _main_folder / "globals.toml"


def get_globals() -> typing.Optional[typing.Dict[str, str]]:
    if _globals_file.is_file():
        try:
            return typing.cast(typing.Dict[str, str], toml.load(_globals_file))
        except Exception as e:
            raise Exception(f"failed to (toml) parse {_globals_file}: {e}")
    return None


class ConfigurationGetter:
    """
    An instance of ConfigurationGetter is used to return instances
    of GlobalConfiguration and instances of Configuration.
    An instance of GlobalConfiguration is a dictionary which
    keys are string which are either "main" (for configuration of SkyGazer)
    or import paths of subclass of SkyThread. The latest indicate to SkyGazer
    which SkyThread classes it should instantiate and run; and using which configuration.
    Values corresponding to the import classes keys are instances of Configuration,
    i.e. dictionaries corresponding to the corresponding SkyThread.
    """

    def get_global(self) -> GlobalConfiguration:
        """
        Returns the global configuration dictionary.
        """
        raise NotImplementedError()

    def get(self, suffix: str) -> Configuration:
        """
        Returns the configuration for the instance of SkyThread corresponding
        to the suffix (import paths are the full key, and can be used as argument,
        but suffix corresponding to the class name are also accepted. e.g. if
        the full key in the global configuration is "package.subpackage.module.class_name",
        passing "class_name" as argument (instead of "package.subpackage.module.class_name")
        is accepted).
        """
        config = self.get_global()
        for key in config.keys():
            if key.endswith(suffix):
                return config[key]
        raise KeyError(f"failed to find the key '{suffix}' in the " "configuration")


def _read_configuration_template(
    path: Path, data: typing.Optional[typing.Dict[str, str]]
) -> Configuration:
    content = path.read_text()
    if data is None:
        return toml.loads(content)
    else:
        template = Template(content)
        fixed_content = template.render(data)
        return toml.loads(fixed_content)


class FixedConfigurationGetter(ConfigurationGetter):
    """
    Subclass of ConfigurationGetter reading instances of GlobalConfiguration
    and of Configuration from a toml file.
    """

    def __init__(
        self,
        path: Path,
        variable_replacement: typing.Optional[typing.Dict[str, str]] = get_globals(),
    ) -> None:
        super().__init__()
        if not path.is_file():
            raise FileNotFoundError(f"failed to find configuration file {path}")
        try:
            self._config = _read_configuration_template(path, variable_replacement)
        except Exception as e:
            raise ValueError(f"Failed to parse configuration file {path}: {e}")

    def get_global(self) -> Configuration:
        return copy.deepcopy(self._config)


class DynamicConfigurationGetter(ConfigurationGetter):
    """
    Subclass of ConfigurationGetter reading instances of GlobalConfiguration
    and of Configuration from a toml file. Contrary to FixedConfigurationGetter,
    the toml file may be rewritten anytime (by another thread). Access to the file
    is protected by locks.Locks.get_lock with the key "configuration"
    (i.e. the "other thread" the updates the files is expected to use this same lock).
    """

    def __init__(
        self,
        path: Path,
        variable_replacement: typing.Optional[typing.Dict[str, str]] = get_globals(),
    ) -> None:
        super().__init__()
        self._lock = Locks.get_lock("configuration")
        self._path = path
        self._variable_replacement = variable_replacement
        self._st_mtime: typing.Optional[float] = None
        self._config: typing.Optional[Configuration] = None

    def get_global(self) -> GlobalConfiguration:
        with self._lock:
            if not self._path.is_file():
                raise FileNotFoundError(
                    f"failed to find configuration file {self._path}"
                )
            if self._st_mtime is None:
                self._st_mtime = os.stat(str(self._path)).st_mtime
            if self._config is not None:
                st_mtime = os.stat(str(self._path)).st_mtime
                if st_mtime == self._st_mtime:
                    return self._config
            try:
                config = _read_configuration_template(
                    self._path, self._variable_replacement
                )
            except Exception as e:
                raise ValueError(
                    f"Failed to parse configuration file {self._path}: {e}"
                )
            self._config = config
            return config


class DictConfigurationGetter(ConfigurationGetter):
    def __init__(self, d: GlobalConfiguration) -> None:
        self._d = d

    def get_global(self) -> GlobalConfiguration:
        return copy.deepcopy(self._d)
