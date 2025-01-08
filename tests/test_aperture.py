import tempfile
from contextlib import contextmanager
from datetime import datetime
from datetime import time as datetime_time
from pathlib import Path

# from nightskycam_focus.adapter import set_aperture, set_focus, Aperture
from typing import Generator

import pytest
import tomli_w
from nightskycam_serialization.status import ApertureRunnerEntries, AsiCamRunnerEntries
from nightskyrunner.config import Config
from nightskyrunner.status import State, Status, wait_for_status

from nightskycam.aperture.runner import (
    Aperture,
    ApertureRunner,
    adapter,
    set_aperture,
    set_focus,
)
from nightskycam.utils.test_utils import (
    ConfigTester,
    configuration_test,
    get_manager,
    runner_started,
    wait_for,
)

# --
# mocking set_focus and set_aperture as the corresponding hardware
# is likely not available on the test server.
# --


class _MockedHardware:
    activated: bool = False
    focus: int = -1
    aperture: Aperture = Aperture.MIN


def mock_set_focus(target_value: int) -> None:
    if not _MockedHardware.activated:
        raise RuntimeError("hardware not activated")
    _MockedHardware.focus = target_value


def mock_set_aperture(target_value: Aperture) -> None:
    if not _MockedHardware.activated:
        raise RuntimeError("hardware not activated")
    _MockedHardware.aperture = target_value


@contextmanager
def mock_adapter():
    try:
        _MockedHardware.activated = True
        yield
    finally:
        _MockedHardware.activated = False


def _datetime_now_time():
    return datetime_time(hour=9, minute=0, second=0)


@pytest.fixture(autouse=True)
def patch_set_focus(mocker):
    mocker.patch(__name__ + ".set_focus", side_effect=mock_set_focus)
    mocker.patch("nightskycam.aperture.runner.set_focus", side_effect=mock_set_focus)


@pytest.fixture(autouse=True)
def patch_set_aperture(mocker):
    mocker.patch(__name__ + ".set_aperture", side_effect=mock_set_aperture)
    mocker.patch(
        "nightskycam.aperture.runner.set_aperture",
        side_effect=mock_set_aperture,
    )


@pytest.fixture(autouse=True)
def patch_adapter(mocker):
    mocker.patch(__name__ + ".adapter", side_effect=mock_adapter)
    mocker.patch("nightskycam.aperture.runner.adapter", side_effect=mock_adapter)


@pytest.fixture(autouse=True)
def patch_datetime_now_time(mocker):
    # Create a mock datetime object with the desired time
    class MockDateTime(datetime):
        @classmethod
        def now(cls):
            return cls(2023, 1, 1, 9, 0)  # January 1, 2023, 9:00 AM

    # Patch the datetime class in the runner module
    mocker.patch("nightskycam.aperture.runner.datetime", MockDateTime)


def test_mocked_functions() -> None:
    with pytest.raises(RuntimeError):
        set_focus(100)
    with adapter():
        set_focus(400)
        set_aperture(Aperture.V1)
    assert _MockedHardware.focus == 400
    assert _MockedHardware.aperture == Aperture.V1


# --------------------------------------------------------------


@pytest.fixture
def tmp_dir(request, scope="function") -> Generator[Path, None, None]:
    """
    Fixture yielding a temp directory and a temp file
    """
    folder_ = tempfile.TemporaryDirectory()
    folder = Path(folder_.name)
    try:
        yield folder
    finally:
        folder_.cleanup()


class _RunnerConfig:
    @classmethod
    def get_config(cls, destination_folder: Path, unsupported: bool = False) -> Config:
        if unsupported:
            return {
                "use": 1,  # not a bool
                "use_zwo_camera": 0,  # not a bool
                "start_time": "10-00",  # not expected format
                "stop_time": "noon",  # not supported
                "focus": -600,  # out of bound
            }
        else:
            return {
                "frequency": 10,
                "use": True,
                "use_zwo_camera": False,
                "start_time": "10:00",
                "stop_time": "17:30",
                "focus": 600,
            }

    @classmethod
    def get_config_tester(cls, destination_folder: Path) -> ConfigTester:
        return ConfigTester(
            cls.get_config(destination_folder, unsupported=False),
            cls.get_config(destination_folder, unsupported=True),
        )


def test_configuration(tmp_dir) -> None:
    """
    Testing instances of CamRunner behave correctly
    to changes of configuration.
    """
    config_tester = _RunnerConfig.get_config_tester(tmp_dir)
    configuration_test(ApertureRunner, config_tester, timeout=30.0)


def test_open_close(tmp_dir) -> None:

    def _write_test_runner_config(config: Config, toml_path: Path) -> None:
        with open(toml_path, "wb") as f:
            tomli_w.dump(config, f)

    def _aperture_closed() -> bool:
        return _MockedHardware.aperture == Aperture.MIN

    def _aperture_opened() -> bool:
        return _MockedHardware.aperture == Aperture.MAX

    def _focus_value() -> int:
        return _MockedHardware.focus

    config: Config = {
        "frequency": 10,
        "use": True,
        "use_zwo_camera": False,
        "start_time": "10:00",
        "stop_time": "17:30",
        "focus": 600,
    }
    config_file = tmp_dir / "test_aperture_config.toml"
    _write_test_runner_config(
        config,
        config_file,
    )

    asi_cam_runner_status = Status("asi_cam_runner", "AsiCamRunner")
    asi_cam_entries = AsiCamRunnerEntries(active="yes")
    asi_cam_runner_status.entries(asi_cam_entries)

    def _set_asi_cam_active():
        status = Status.retrieve("asi_cam_runner")
        asi_cam_entries = AsiCamRunnerEntries(active="yes")
        status.entries(asi_cam_entries)

    def _set_asi_cam_inactive():
        status = Status.retrieve("asi_cam_runner")
        asi_cam_entries = AsiCamRunnerEntries(active="no")
        status.entries(asi_cam_entries)

    with get_manager((ApertureRunner, config_file)):
        wait_for(runner_started, True, args=(ApertureRunner.__name__,))
        wait_for_status(ApertureRunner.__name__, State.running, timeout=2.0)
        # the starting config uses the interval 10AM to 5:30PM, and time now
        # is mocked to 9AM. Therefore the aperture should open.
        wait_for(_aperture_opened, True)
        # changing the inverval to 8AM. Therefore the aperture should close
        config["start_time"] = "8:00"
        _write_test_runner_config(config, config_file)
        wait_for(_aperture_closed, True)
        # now activating the zwo asi camera and setting "use_zwo_camera" to True:
        # the aperture should open
        _set_asi_cam_active()
        config["use_zwo_camera"] = True
        _write_test_runner_config(config, config_file)
        wait_for(_aperture_opened, True)
        # setting the camera to inactive, the aperture should close
        _set_asi_cam_inactive()
        wait_for(_aperture_closed, True)
        # stop using the zwo asi camera, the aperture should open
        # (because 8am)
        _set_asi_cam_active()
        config["use_zwo_asi"] = False
        _write_test_runner_config(config, config_file)
        wait_for(_aperture_opened, True)
        # changing the focus
        assert _MockedHardware.focus == 600
        config["focus"] = 550
        _write_test_runner_config(config, config_file)
        wait_for(_focus_value, 550)
        # using zwo asi again
        _set_asi_cam_inactive()
        config["use_zwo_asi"] = True
        _write_test_runner_config(config, config_file)
        wait_for(_aperture_closed, True)
        # stop using the aperture adapter altogether
        config["use"] = False
        _write_test_runner_config(config, config_file)
        wait_for(_aperture_opened, True)
        # sanity check the runner is still running
        wait_for_status(ApertureRunner.__name__, State.running, timeout=2.0)
