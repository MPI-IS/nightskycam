"""
Tests for the [nightskycam.process.runner.ImageProcessRunner](process runner).
"""

import os
import pprint
import random
import tempfile
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Tuple

import numpy as np
import pytest
from nightskycam.process.runner import (
    ImageProcessRunner,
    _process,
    _save_files,
)
from nightskycam.process.stretch import stretch_methods
from nightskycam.utils.file_saving import save_npy, supported_file_formats
from nightskycam.utils.filename import get_filename
from nightskycam.utils.test_utils import (
    ConfigTester,
    configuration_test,
    had_error,
    get_manager,
    get_runner_error,
    runner_started,
    wait_for,
)
from nightskyrunner.config import Config


def _darkframes_file() -> Path:
    # there is a darkframe file in the "darkframes" subfolder of the
    # test folder.

    p = (
        Path(os.path.abspath(__file__)).parent
        / "darkframes"
        / "darkframes.hdf5"
    )
    if not p.is_file():
        raise FileNotFoundError(
            f"failed to find darkframes file {p}, required for the tests"
        )
    return p


@contextmanager
def _delete_files(perform: bool, *files: Path) -> Generator[None, None, None]:
    # makes sure the files are deleted upon exit

    try:
        yield
    finally:
        if perform:
            for f in files:
                if f.is_file():
                    f.unlink()


@pytest.fixture
def tmp_dirs(
    request, scope="function"
) -> Generator[Tuple[Path, Path, Path], None, None]:
    """
    Fixture yielding a tuple of three temp directories.
    """

    folders_ = [tempfile.TemporaryDirectory() for _ in range(3)]
    folders = [Path(f_.name) for f_ in folders_]
    try:
        yield tuple(folders)  # type: ignore
    finally:
        for f in folders_:
            f.cleanup()


def _get_camera_like_image(
    camera_shape: Tuple[int, int] = (2822, 4144), dtype=np.uint16
) -> np.ndarray:
    """
    Returns an image, same format as the capture from
    a zwo asi camera.
    """

    rng = np.random.default_rng()
    if np.issubdtype(dtype, np.floating):
        return rng.random(camera_shape, dtype=dtype)
    elif np.issubdtype(dtype, np.integer):
        max_val = np.iinfo(dtype).max
        return rng.integers(
            low=0, high=max_val, size=camera_shape, dtype=dtype
        )
    else:
        raise ValueError(f"Unsupported dtype: {dtype}")


def _get_meta(
    meta_temperature: Optional[int] = None,
    meta_exposure: Optional[int] = None,
) -> Dict:
    # returns a dictionary of meta data suitable
    # for darkframe substraction.

    r: Dict[str, Any] = {"controllables": {}}
    if meta_temperature:
        r["controllables"]["Temperature"] = meta_temperature * 10
    if meta_exposure:
        r["controllables"]["Exposure"] = meta_exposure
    return r


class _ImagesWriter:
    # for writing image files in format suitable for
    # instances of ProcessRunner. Will write both the
    # npy file (image) and the toml file (meta data)

    def __init__(
        self,
        target_folder: Path,
        start_date: str = "2023_01_01_01_01_00",
        system_name: str = "test_system",
    ) -> None:
        if not target_folder.is_dir():
            raise FileNotFoundError()
        self._target_folder = target_folder
        self._start_date = datetime.strptime(start_date, "%Y_%m_%d_%H_%M_%S")
        self._nb_files = 0
        self._system_name = system_name

    def write(
        self,
        nb_files: int,
        meta_temperature: Optional[int] = None,
        meta_exposure: Optional[int] = None,
    ) -> List[Tuple[Path, Path]]:
        r: List[Tuple[Path, Path]] = []
        meta = _get_meta(meta_temperature, meta_exposure)
        for _ in range(nb_files):
            self._nb_files += 1
            next_date = self._start_date + timedelta(
                minutes=5 * self._nb_files
            )
            filename = get_filename(self._system_name, next_date)
            image = _get_camera_like_image()
            img_path, meta_path = save_npy(
                image, meta, filename, self._target_folder
            )
            r.append((img_path, meta_path))
        return r


class _ImageProcessRunnerConfig:
    # for running
    # nightskycam.utils.test_utils.configuration_test

    @classmethod
    def get_config(
        cls,
        source_folder: Path,
        destination_folder: Path,
        latest_folder: Path,
        darkframes_file: Optional[Path],
        unsupported: bool = False,
    ) -> Config:
        if unsupported:
            return {
                "darkframes": "/not/a/valid/path",
                "fileformat": "unknown_format",
                "stretch": "unknown_stretch_method",
                "resize": -5,
                "resize_interpolation": "INVALID_INTERPOLATION",
                "debayer": "INVALID_DEBAYER",
            }
        else:
            return {
                "frequency": 5.0,
                "source_folder": str(source_folder),
                "latest_folder": str(latest_folder),
                "destination_folder": str(destination_folder),
                "darkframes": str(darkframes_file) if darkframes_file else "",
                "fileformat": "tiff",
                "stretch": "auto_stretch",
                "resize": 2.0,
                "resize_interpolation": "INTER_NEAREST",
                "eight_bits": False,
                "debayer": "COLOR_BAYER_BG2BGR",
            }

    @classmethod
    def get_config_tester(
        cls,
        source_folder: Path,
        destination_folder: Path,
        latest_folder: Path,
        darkframes_file: Optional[Path],
    ) -> ConfigTester:
        return ConfigTester(
            cls.get_config(
                source_folder,
                destination_folder,
                latest_folder,
                darkframes_file,
                unsupported=False,
            ),
            cls.get_config(
                source_folder,
                destination_folder,
                latest_folder,
                darkframes_file,
                unsupported=True,
            ),
        )


def test_configuration(tmp_dirs) -> None:
    """
    Testing instances of ImageProcessRunner behave correctly
    to changes of configuration.
    """
    source_folder, destination_folder, latest_folder = tmp_dirs

    config_tester = _ImageProcessRunnerConfig.get_config_tester(
        source_folder,
        destination_folder,
        latest_folder,
        _darkframes_file(),
    )

    iw = _ImagesWriter(source_folder)
    iw.write(100, meta_temperature=20, meta_exposure=150000)
    configuration_test(ImageProcessRunner, config_tester, timeout=30.0)


def _test_manager_config(config: Config) -> None:
    # spawn a nightskyrunner manager and an instance of
    # ImageProcessRunner which will process images using
    # the config passed as argument.,

    def _folder_empty(p: Path) -> bool:
        return not any(p.iterdir())

    with get_manager((ImageProcessRunner, config)):
        wait_for(runner_started, True, args=(ImageProcessRunner.__name__,))
        assert not had_error(ImageProcessRunner.__name__)
        iw = _ImagesWriter(Path(str(config["source_folder"])))
        iw.write(
            1,
            meta_temperature=random.choice((10, 20, 30)),
            meta_exposure=random.choice((50000, 100000, 150000, 300000)),
        )
        try:
            wait_for(
                _folder_empty,
                True,
                args=(Path(str(config["source_folder"])),),
                timeout=3.0,
            )
        except RuntimeError:
            error_message = get_runner_error(ImageProcessRunner.__name__)
            error_message_ = (
                f"error:\n{error_message}" if error_message else ""
            )
            error = str(
                f"this configuration failed:\n{pprint.pformat(config)}\n"
                f"{error_message_}"
            )
            raise RuntimeError(error)
        assert not had_error(ImageProcessRunner.__name__)


def test_runner(tmp_dirs) -> None:
    """
    Run instances of ImageProcessRunner with various configurations.
    """

    source_folder, destination_folder, latest_folder = tmp_dirs
    configs: List[Config] = [
        {
            "frequency": 5.0,
            "stretch": "auto_stretch",
            "debayer": "COLOR_BAYER_BG2BGR",
            "resize": 2.0,
            "resize_interpolation": "INTER_NEAREST",
            "eight_bits": True,
            "fileformat": "tiff",
            "darkframes": _darkframes_file(),
        },
        {
            "frequency": 5.0,
            "debayer": "COLOR_BAYER_BG2BGR",
            "resize": 1.0,
            "resize_interpolation": "INTER_NEAREST",
            "eight_bits": False,
            "fileformat": "npy",
            "darkframes": _darkframes_file(),
        },
        {
            "frequency": 5.0,
            "stretch": "AsinhStretch",
            "debayer": "COLOR_BAYER_BG2BGR",
            "resize": 1.0,
            "resize_interpolation": "INTER_NEAREST",
            "eight_bits": True,
            "fileformat": "jpeg",
            "jpeg_quality": 95,
            "darkframes": _darkframes_file(),
        },
        {
            "frequency": 5.0,
            "stretch": "AsinhStretch",
            "debayer": "COLOR_BAYER_BG2BGR",
            "resize": 1.0,
            "resize_interpolation": "INTER_NEAREST",
            "eight_bits": True,
            "fileformat": "jpeg",
            "jpeg_quality": 95,
            "darkframes": "None",
        },
    ]
    base_config = {
        "frequency": 5.0,
        "source_folder": str(source_folder),
        "latest_folder": str(latest_folder),
        "destination_folder": str(destination_folder),
    }

    for config in configs:
        for k, v in base_config.items():
            config[k] = v
        _test_manager_config(config)


def _test_config(
    config: Config,
    filename: str,
    meta_temperature: Optional[int] = None,
    meta_exposure: Optional[int] = None,
    delete_files: bool = True,
) -> None:
    # Calls the _process and _save_files functions with the
    # config passed as argument. _process and _save_files are
    # the main function used by ImageProcessRunner, so this
    # is almost as good as testing ImageProcessRunner, just faster.

    try:
        source_folder = Path(str(config["source_folder"]))
        destination_folder = Path(str(config["destination_folder"]))
        im = _ImagesWriter(source_folder)
        npy_file, meta_file = im.write(1, meta_temperature, meta_exposure)[0]

        with _delete_files(
            delete_files,
            npy_file,
            meta_file,
            destination_folder / f"{filename}.toml",
            destination_folder / f"{filename}.{config['fileformat']}",
        ):
            image, _ = _process(config, npy_file, meta_file)
            _save_files(config, image, {}, filename, destination_folder)
            assert (destination_folder / f"{filename}.toml").is_file()
            assert (
                destination_folder / f"{filename}.{config['fileformat']}"
            ).is_file()
    except Exception as e:
        error = str(
            f"this configuration failed:\n{pprint.pformat(config)}\n"
            f"error type: {type(e)}\n"
            f"error message: {e}"
        )
        raise RuntimeError(error)


def test_process(tmp_dirs) -> None:
    """
    Test the _process function with a wide
    range of configurations
    """

    source_folder, destination_folder, latest_folder = tmp_dirs

    _configs = {
        "stretch": stretch_methods,
        "debayer": ("COLOR_BAYER_BG2BGR",),
        "resize": (0.5, 1.0, 2.0),
        "resize_interpolation": ("INTER_NEAREST",),
        "eight_bits": (True, False),
        "fileformat": supported_file_formats,
        "jpeg_quality": (100, 90),
        "darkframes": (None, _darkframes_file()),
    }

    def _get_random_config(key: str, value: Any) -> Dict[str, Any]:
        d = {k: random.choice(values) for k, values in _configs.items()}
        d[key] = value
        d = {k: v for k, v in d.items() if v is not None}
        return d

    base_config = {
        "frequency": 5.0,
        "source_folder": str(source_folder),
        "latest_folder": str(latest_folder),
        "destination_folder": str(destination_folder),
    }

    for key, values in _configs.items():
        for value in values:
            config = _get_random_config(key, value)
            for k, v in base_config.items():
                config[k] = v
            print()
            print(key, value)
            pprint.pprint(config)
            print()
            try:
                _test_config(
                    config,
                    "test",
                    meta_temperature=20,
                    meta_exposure=150000,
                    delete_files=True,
                )
            except RuntimeError as e:
                raise RuntimeError(f"when testing {key} ({value}), {e}")
