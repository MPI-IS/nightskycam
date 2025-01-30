"""
Module for testing [nightskycam.cams.runner.CamRunner]() and related utilities.
"""

import datetime
import tempfile
import time
from contextlib import suppress
from pathlib import Path
from typing import Generator, List

import pytest
from nightskycam.cams import utils
from nightskycam.cams.runner import CamRunner
from nightskycam.dummycams.runner import DummyCamRunner
from nightskycam.location_info.runner import LocationInfoRunner
from nightskycam.utils.test_utils import (
    ConfigTester,
    configuration_test,
    had_error,
    get_manager,
    runner_started,
    wait_for,
)
from nightskyrunner.config import Config
from nightskyrunner.shared_memory import SharedMemory
from nightskyrunner.status import State, wait_for_status


@pytest.fixture
def reset_memory(
    request,
    scope="function",
) -> Generator[None, None, None]:
    """
    Fixture clearing the nightskyrunner shared memory
    upon exit.
    """
    yield None
    SharedMemory.clear()


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


def test_period_active_night() -> None:
    """
    testing utils._period_active
    """

    start = datetime.time(19, 30, 0)
    end = datetime.time(9, 15, 0)

    for now in (
        datetime.time(19, 45, 1),
        datetime.time(0, 10, 34),
        datetime.time(0, 0, 0),
        datetime.time(23, 0, 0),
        datetime.time(8, 55, 45),
    ):
        assert utils._period_active(start, end, now)

    for now in (
        datetime.time(18, 45, 1),
        datetime.time(12, 10, 34),
        datetime.time(9, 16, 2),
        datetime.time(14, 0, 0),
        datetime.time(19, 25, 45),
    ):
        assert not utils._period_active(start, end, now)


def test_period_active_day() -> None:
    """
    testing utils._period_active
    """

    start = datetime.time(10, 30, 0)
    end = datetime.time(13, 45, 0)

    for now in (
        datetime.time(11, 45, 1),
        datetime.time(12, 10, 34),
        datetime.time(13, 12, 0),
    ):
        assert utils._period_active(start, end, now)

    for now in (
        datetime.time(14, 45, 1),
        datetime.time(9, 10, 34),
        datetime.time(0, 0, 0),
    ):
        assert not utils._period_active(start, end, now)


def test_is_active() -> None:
    """
    testing utils.is_active
    """

    start = datetime.time(19, 30, 0)
    end = datetime.time(9, 15, 0)

    use_sun_alt = True
    use_weather = True
    night = True
    cloud_cover = 40
    cloud_cover_threshold = 50
    weather = None
    pause = False

    days: List[datetime.time] = [
        datetime.time(10, 35, 0),
        datetime.time(12, 10, 10),
        datetime.time(13, 10, 12),
        datetime.time(19, 10, 45),
    ]

    nights: List[datetime.time] = [
        datetime.time(20, 30, 0),
        datetime.time(0, 20, 0),
        datetime.time(22, 45, 2),
        datetime.time(9, 0, 30),
    ]

    various_dtimes: List[datetime.time] = days + nights

    for dtime_now in various_dtimes:
        # night is True, use_sun_alt is True,
        # (and cloud_cover < cloud_cover_threshold)
        # so dtime_now does not matter
        assert utils.is_active(
            start,
            end,
            use_sun_alt,
            use_weather,
            night,
            cloud_cover,
            cloud_cover_threshold,
            weather,
            dtime_now,
            pause,
        )[0]

    use_sun_alt = False
    use_weather = False
    night = True
    cloud_cover = 40
    cloud_cover_threshold = 50
    weather = None

    for dtime_now in days:
        assert not utils.is_active(
            start,
            end,
            use_sun_alt,
            use_weather,
            night,
            cloud_cover,
            cloud_cover_threshold,
            weather,
            dtime_now,
            pause,
        )[0]

    for dtime_now in nights:
        assert utils.is_active(
            start,
            end,
            use_sun_alt,
            use_weather,
            night,
            cloud_cover,
            cloud_cover_threshold,
            weather,
            dtime_now,
            pause,
        )[0]

    pause = True
    for dtime_now in nights:
        assert not utils.is_active(
            start,
            end,
            use_sun_alt,
            use_weather,
            night,
            cloud_cover,
            cloud_cover_threshold,
            weather,
            dtime_now,
            pause,
        )[0]


def _set_local_info(
    night: bool, weather: str, cloud_cover: int, time_stamp: float
) -> None:
    # write local infos in the shared memory, mocking
    # what LocationInfoRunner does

    memory = SharedMemory.get(LocationInfoRunner.sm_key)
    memory["night"] = night
    memory["weather"] = weather
    memory["cloud_cover"] = cloud_cover
    memory["time_stamp"] = time_stamp


def _set_failed_local_info(time_stamp: float) -> None:
    memory = SharedMemory.get(LocationInfoRunner.sm_key)
    with suppress(KeyError):
        del memory["night"]
        del memory["weather"]
        del memory["cloud_cover"]
    memory["time_stamp"] = time_stamp


def test_get_local_info(reset_memory) -> None:
    """
    Testing utils.get_local_info
    """

    get_night, get_weather, get_cloud_cover = utils.get_local_info()
    assert get_night is None
    assert get_weather is None
    assert get_cloud_cover is None

    def _wait_for_local_info(
        night: bool, weather: str, cloud_cover: int
    ) -> bool:
        get_night, get_weather, get_cloud_cover = utils.get_local_info()
        return all(
            [
                a == b
                for a, b in zip(
                    (night, weather, cloud_cover),
                    (get_night, get_weather, get_cloud_cover),
                )
            ]
        )

    night = True
    weather = "cloudy"
    cloud_cover = 70
    time_stamp = time.time()

    _set_local_info(night, weather, cloud_cover, time_stamp)
    wait_for(_wait_for_local_info, True, args=(night, weather, cloud_cover))

    time.sleep(0.2)
    get_night, get_weather, get_cloud_cover = utils.get_local_info(
        deprecation=0.15
    )
    assert get_night is None
    assert get_weather is None
    assert get_cloud_cover is None


class _RunnerConfig:
    @classmethod
    def get_config(
        cls, destination_folder: Path, unsupported: bool = False
    ) -> Config:
        if unsupported:
            return {
                "frequency": 0.0,
                "start_time": "25:30",
                "end_time": "2022:12:04:08:56",
                "cloud_cover_threshold": "not an int",
                "pause": 45,  # i.e. not a bool
            }
        else:
            return {
                "frequency": 5.0,
                "destination_folder": str(destination_folder),
                "start_time": "19:30",
                "end_time": "08:00",
                "use_sun_alt": True,
                "use_weather": True,
                "cloud_cover_threshold": 50,
                "nightskycam": "test_system",
                "pause": False,
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
    configuration_test(DummyCamRunner, config_tester, timeout=30.0)


def _list_files(target_folder: Path) -> List[Path]:
    # list the content of target_folder

    r: List[Path] = []
    for item in target_folder.iterdir():
        if item.is_file():
            r.append(item.absolute())
    return r


def test_cam_runner(tmp_dir) -> None:
    """
    Tests an instance of DummyCamRunner runs without
    switching to error mode.
    """

    def _image_generated(destination_folder: Path) -> bool:
        # returns True if destination_folder contains
        # at least one npy and one toml file

        files = _list_files(destination_folder)
        npy = any([str(f).endswith(".npy") for f in files])
        toml = any([str(f).endswith(".toml") for f in files])
        return npy and toml

    # setting a config for which pictures should be taken
    night = True
    weather = "cloudy"
    cloud_cover = 60
    time_stamp = time.time()

    _set_local_info(night, weather, cloud_cover, time_stamp)

    config: Config = {
        "frequency": 5.0,
        "destination_folder": str(tmp_dir),
        "start_time": "19:30",
        "end_time": "08:00",
        "use_sun_alt": True,
        "use_weather": True,
        "cloud_cover_threshold": 70,
        "nightskycam": "test_system",
        "pause": False,
    }

    with get_manager((DummyCamRunner, config)):
        # checking the runner is not in error states and write
        # pictures in tmp_dir
        wait_for(runner_started, True, args=(DummyCamRunner.__name__,))
        wait_for_status(DummyCamRunner.__name__, State.running, timeout=2.0)
        assert not had_error(DummyCamRunner.__name__)
        wait_for(_image_generated, True, args=(tmp_dir,))
        assert not had_error(DummyCamRunner.__name__)


def test_wait_duration() -> None:
    """
    Tests CamRunner._wait_duration
    """

    frequency = 1.0

    now1 = datetime.time(12, 15, 10, 5000)
    now2 = datetime.time(12, 15, 10, 601)

    next1, sleep1 = CamRunner._wait_duration(frequency, now1)
    next2, sleep2 = CamRunner._wait_duration(frequency, now2)

    assert next1 == next2
    assert next1 == 12 * 3600 + 15 * 60 + 11

    assert sleep1 == pytest.approx(1.0 - 5000 * 1e-6)
    assert sleep2 == pytest.approx(1.0 - 601 * 1e-6)


def test_no_local_info(tmp_dir) -> None:

    time_stamp = time.time()
    _set_failed_local_info(time_stamp)

    config: Config = {
        "frequency": 5.0,
        "destination_folder": str(tmp_dir),
        "start_time": "19:30",
        "end_time": "08:00",
        "use_sun_alt": True,
        "use_weather": True,
        "cloud_cover_threshold": 70,
        "nightskycam": "test_system",
        "pause": False,
    }

    with get_manager((DummyCamRunner, config)):
        wait_for(runner_started, True, args=(DummyCamRunner.__name__,))
        wait_for_status(DummyCamRunner.__name__, State.running, timeout=2.0)
        assert not had_error(DummyCamRunner.__name__)
