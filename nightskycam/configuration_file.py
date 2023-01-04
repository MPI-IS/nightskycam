import logging
import importlib
import typing
import toml
from pathlib import Path
from .skythread import SkyThread
from .types import GlobalConfiguration
from .configuration_getter import FixedConfigurationGetter

_nightskycam_config_folder = Path("/opt/nightskycam")

_logger = logging.getLogger("configuration_file")


def configuration_file_folder() -> Path:
    if not _nightskycam_config_folder.is_dir():
        raise RuntimeError(
            f"nightskycam configuration folder ({_nightskycam_config_folder}) could not be found"
        )
    if not _nightskycam_config_folder.is_symlink():
        return _nightskycam_config_folder
    r = _nightskycam_config_folder.parent / _nightskycam_config_folder.readlink()
    return r


def _get_class(class_path: str) -> typing.Type:
    """
    class_path: something like "package.subpackage.module.class_name".
    Imports package.subpackage.module and returns the class.
    """

    # class_path is only the name of the class, which is thus expected
    # to be in global scope
    if "." not in class_path:
        try:
            class_ = globals()[class_path]
        except KeyError:
            raise ValueError(
                f"class {class_path} could not be found in the global scope"
            )

    # importing the package the class belongs to
    to_import, class_name = class_path.rsplit(".", 1)
    try:
        imported = importlib.import_module(to_import)
    except ModuleNotFoundError as e:
        raise ValueError(
            f"failed to import {to_import} (needed to instantiate {class_path}): {e}"
        )

    # getting the class
    try:
        class_ = getattr(imported, class_name)
    except AttributeError:
        raise ValueError(
            f"class {class_name} (provided path: {class_path}) could not be found"
        )

    return class_


def get_skythreads(config: GlobalConfiguration) -> typing.List[typing.Type[SkyThread]]:

    # all keys are expected to be class paths, e.g. nightskycam.FtpThread
    # (except of the key named "main")
    class_names: typing.List[str] = [k for k in config.keys() if k != "main"]

    # importing all the related classes
    classes: typing.List[typing.Type[SkyThread]] = []
    for class_name in class_names:
        try:
            class_ = _get_class(class_name)
        except Exception as e:
            _logger.error(f"configuration error: {e}")
        else:
            classes.append(class_)

    # checking all these classes are indeed subclasses of SkyThread
    for class_ in classes:
        if not issubclass(class_, SkyThread):
            _logger.error(
                "the configuration request the use of a thread based on the "
                f"class {class_}, but this class is not a subclass of SkyThread"
            )

    return [class_ for class_ in classes if issubclass(class_, SkyThread)]


def is_a_valid_config_file(path: Path) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"failed to find configuration file {path.name}")
    try:
        content = toml.load(path)
    except Exception as e:
        raise ValueError(
            f"failed to (toml) parse the configuration file {path.name}: {e}"
        )
    try:
        main_config = content["main"]
    except KeyError:
        raise KeyError(
            f"failed to find the required key 'main' in the "
            f"configuration file {path.name}"
        )
    required_keys = ("period",)
    for rk in required_keys:
        if rk not in main_config.keys():
            raise KeyError(
                f"failed find the key main/{rk} in configuration file {path.name}"
            )
    try:
        float(main_config["period"])
    except ValueError as e:
        raise ValueError(
            f"failed to cast the value {main_config['period']} of main/{rk} "
            f"to a float: {e}"
        )
    try:
        classes = get_skythreads(typing.cast(GlobalConfiguration, content))
    except Exception as e:
        raise e.__class__(
            f"import error when parsing configuration file {path.name}: {e}"
        )

    config_getter = FixedConfigurationGetter(path)

    errors_: typing.List[typing.Optional[str]] = [
        class_.check_config(config_getter) for class_ in classes
    ]
    errors = [e for e in errors_ if e is not None]
    if errors:
        errors_list = " || ".join(errors)
        raise ValueError(
            f"the following errors where found in configuration file {path.name}: "
            f"{errors_list}"
        )


def is_valid_configuration_filename(filename: str) -> bool:
    """
    A valid configutation file name is of the format
    'nightskycam_config_{version}.toml' where
    {version} must be an int.
    """
    if not filename.startswith("nightskycam_config_"):
        return False
    if not filename.endswith(".toml"):
        return False
    parts = filename[:-5].split("_")
    if len(parts) != 3:
        return False
    try:
        int(parts[2])
    except ValueError:
        return False
    return True


def list_local_config_files(folder: Path) -> typing.List[str]:
    """
    List all the valid configuration files located in 'path'
    (no recursive search).
    """
    content_paths = folder.glob("nightskycam_config_*.toml")
    content_files = [f for f in content_paths if f.is_file()]
    return [f.name for f in content_files if is_valid_configuration_filename(f.name)]


def get_version_number(filename: str) -> int:
    if not is_valid_configuration_filename(filename):
        raise ValueError(
            f"can not get a version number from {filename}: "
            f"not a valid nightskycam configuration file name "
        )
    return int(filename[:-5].split("_")[2])


def best_config_file(filenames: typing.List[str]) -> str:
    """
    Returns the 'best' configuration file name from a list configuration file names.
    Is the best the one with the highest version number
    """
    versions = {get_version_number(filename): filename for filename in filenames}
    return versions[max(versions.keys())]


def local_config_cleanup(folder: Path, main_file: str) -> None:
    """
    List all the configuration files in path ('nightskycam_*_*.toml'),
    select the 'best' (see ConfigThreadConfiguration documentation),
    deleted the other, and setup 'nightskycam.toml' to be a symlink to this
    file.
    """
    local_files = list_local_config_files(folder)
    best_file = best_config_file(local_files)
    main_path = folder / main_file
    try:
        main_path.unlink()
    except Exception:
        pass
    main_path.symlink_to(best_file)
    to_delete = [
        folder / filename for filename in local_files if not filename == best_file
    ]
    for path in to_delete:
        path.unlink()


def current_config_file() -> str:
    folder = configuration_file_folder()
    config_file = folder / "nightskycam_config.toml"
    if not config_file.is_file():
        raise FileNotFoundError(f"failed to find the configuration file {config_file}")
    if not config_file.is_symlink():
        return config_file.name
    return config_file.readlink().name


