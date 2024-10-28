import datetime
import tempfile
import time
from pathlib import Path
from typing import Generator, Optional, Tuple

import pytest
from nightskycam.sleepypi.runner import (SleepyPiRunner, _duration_to_event,
                                         _should_sleep, _sleep_duration,
                                         _time_to_sleep)
from nightskycam.utils.test_utils import (ConfigTester, configuration_test,
                                          exception_on_error_state,
                                          get_manager, runner_started,
                                          wait_for)
from nightskyrunner.config import Config
from nightskyrunner.status import State, wait_for_status


@pytest.fixture
def tmp_dirs(request, scope="function") -> Generator[Tuple[Path, Path], None, None]:
    """
    Fixture yielding a temp directory and a temp file
    """
    folder_ftp_ = tempfile.TemporaryDirectory()
    folder_ftp = Path(folder_ftp_.name)
    folder_tty_ = tempfile.TemporaryDirectory()
    folder_tty = Path(folder_tty_.name)
    tty_file = folder_tty / "tty.txt"
    tty_file.touch()
    try:
        yield folder_ftp, tty_file
    finally:
        folder_ftp_.cleanup()
        folder_tty_.cleanup()


class _SleepyPiRunnerConfig:
    @classmethod
    def get_config(
        cls, ftp_folder: Path, tty_file: Path, unsupported: bool = False
    ) -> Config:
        if unsupported:
            return {
                "start_sleep": "123:293",
                "stop_sleep": "1234/13w",
                "sleep": "true",  # not a bool
                "wait_ftp": 1,  # not a bool
            }
        else:
            return {
                "frequency": 5.0,
                "tty": str(tty_file),
                "sleep": True,
                "start_sleep": "09:30",
                "stop_sleep": "18:00",
                "ftp_folder": str(ftp_folder),
                "wait_ftp": True,
            }

    @classmethod
    def get_config_tester(cls, ftp_folder: Path, tty_file: Path) -> ConfigTester:
        return ConfigTester(
            cls.get_config(ftp_folder, tty_file, unsupported=False),
            cls.get_config(ftp_folder, tty_file, unsupported=True),
        )


def test_configuration(tmp_dirs) -> None:
    """
    Testing instances of SleepyPiRunner behave correctly
    to changes of configuration.
    """
    ftp_folder, tty_file = tmp_dirs

    config_tester = _SleepyPiRunnerConfig.get_config_tester(ftp_folder, tty_file)
    configuration_test(SleepyPiRunner, config_tester, timeout=30.0)


def test_duration_to_event() -> None:

    event = datetime.time(10, 15, 0)

    time_now = datetime.time(10, 12, 0)
    assert _duration_to_event(event, time_now) == 3

    time_now = datetime.time(9, 50, 0)
    assert _duration_to_event(event, time_now) == 25

    time_now = datetime.time(10, 16, 0)
    assert _duration_to_event(event, time_now) == 60 * 24 - 1


def test_should_sleep_no_ftp() -> None:

    # 10:30 am
    start_sleep = datetime.time(10, 30, 0)

    # 15:35 pm
    stop_sleep = datetime.time(15, 35, 0)

    # testing whenb ftp_folder is None, i.e. no wait
    # for ftp to be uploaded

    # before sleep time
    time_now = datetime.time(10, 5, 0)
    sleep, _, min_to_sleep = _should_sleep(
        None, start_sleep, stop_sleep, time_now=time_now
    )
    assert not sleep
    # number of mintes between 10:05 and 10:30
    assert min_to_sleep == 25

    # after sleep time
    time_now = datetime.time(23, 15, 0)
    sleep, _, min_to_sleep = _should_sleep(
        None, start_sleep, stop_sleep, time_now=time_now
    )
    assert not sleep
    # number of minutes between 23:15 and 10:30
    assert min_to_sleep == 10 * 60 + 30 + 45

    # between start and stop sleep
    time_now = datetime.time(14, 40, 0)
    sleep, _, min_to_sleep = _should_sleep(
        None, start_sleep, stop_sleep, time_now=time_now
    )
    assert sleep


def test_should_sleep_ftp(tmp_dirs) -> None:

    ftp_folder, _ = tmp_dirs

    ftp_file = ftp_folder / "test.txt"
    ftp_file.touch()

    # 10:30 am
    start_sleep = datetime.time(10, 30, 0)

    # 15:35 pm
    stop_sleep = datetime.time(15, 35, 0)

    for time_now in (
        datetime.time(10, 5, 0),
        datetime.time(23, 15, 0),
        datetime.time(14, 40, 0),
    ):
        sleep, _, __ = _should_sleep(
            ftp_folder, start_sleep, stop_sleep, time_now=time_now
        )
        assert not sleep

    ftp_file.unlink()

    # before sleep time
    time_now = datetime.time(10, 5, 0)
    sleep, _, min_to_sleep = _should_sleep(
        None, start_sleep, stop_sleep, time_now=time_now
    )
    assert not sleep
    # number of mintes between 10:05 and 10:30
    assert min_to_sleep == 25

    # between start and stop sleep
    time_now = datetime.time(14, 40, 0)
    sleep, _, min_to_sleep = _should_sleep(
        None, start_sleep, stop_sleep, time_now=time_now
    )
    assert sleep


def _read_file_content(file_path: Path) -> Optional[str]:
    if file_path.stat().st_size == 0:
        return None
    else:
        with open(file_path, "r") as file:
            content = file.read()
        return content


def test_sleep_duration() -> None:

    time_now = datetime.time(hour=9, minute=24)
    stop_sleep = datetime.time(hour=9, minute=51)
    assert _sleep_duration(time_now, stop_sleep) == 27

    time_now = datetime.time(hour=9, minute=50)
    stop_sleep = datetime.time(hour=14, minute=4)
    assert _sleep_duration(time_now, stop_sleep) == 254

    time_now = datetime.time(hour=22, minute=0)
    stop_sleep = datetime.time(hour=8, minute=0)
    assert _sleep_duration(time_now, stop_sleep) == 600

    time_now = datetime.time(hour=22, minute=0)
    stop_sleep = datetime.time(hour=6, minute=12)
    assert _sleep_duration(time_now, stop_sleep) == 492

    time_now = datetime.time(hour=12, minute=0)
    stop_sleep = datetime.time(hour=12, minute=0)
    assert _sleep_duration(time_now, stop_sleep) == 0

    time_now = datetime.time(hour=12, minute=0)
    stop_sleep = datetime.time(hour=11, minute=30)
    assert _sleep_duration(time_now, stop_sleep) == 1410


def test_sleepypi_runner_not_sleep(tmp_dirs, mocker) -> None:

    ftp_folder, tty_file = tmp_dirs

    config: Config = {
        "frequency": 5.0,
        "tty": str(tty_file),
        "sleep": True,
        "start_sleep": "09:30",
        "stop_sleep": "18:00",
        "ftp_folder": str(ftp_folder),
        "wait_ftp": True,
        "override_sleep_blocked": True,
    }

    def _now_is_8am() -> datetime.time:
        return datetime.time(8, 0, 0)

    mocked_datetime_now = mocker.patch(
        "nightskycam.sleepypi.runner._now", side_effect=_now_is_8am
    )

    with get_manager((SleepyPiRunner, config)):
        # running an in stance of SpaceKeeperRunner
        wait_for(runner_started, True, args=(SleepyPiRunner.__name__,))
        wait_for_status(SleepyPiRunner.__name__, State.running, timeout=2.0)
        wait_for(lambda: mocked_datetime_now.call_count > 0, True)
        time.sleep(0.5)
        exception_on_error_state(SleepyPiRunner.__name__)
        assert _read_file_content(tty_file) is None


def test_sleepypi_runner_sleep(tmp_dirs, mocker) -> None:

    ftp_folder, tty_file = tmp_dirs

    config: Config = {
        "frequency": 5.0,
        "tty": str(tty_file),
        "sleep": True,
        "start_sleep": "09:30",
        "stop_sleep": "18:00",
        "ftp_folder": str(ftp_folder),
        "wait_ftp": True,
        "override_sleep_blocked": True,
    }

    def _now_is_11am() -> datetime.time:
        return datetime.time(11, 0, 0)

    mocked_datetime_now = mocker.patch(
        "nightskycam.sleepypi.runner._now", side_effect=_now_is_11am
    )

    with get_manager((SleepyPiRunner, config)):
        # running an in stance of SpaceKeeperRunner
        wait_for(runner_started, True, args=(SleepyPiRunner.__name__,))
        wait_for_status(SleepyPiRunner.__name__, State.running, timeout=2.0)
        wait_for(lambda: mocked_datetime_now.call_count > 0, True)
        exception_on_error_state(SleepyPiRunner.__name__)
        assert "sleep:" in str(_read_file_content(tty_file))


def test_sleepypi_runner_ftp(tmp_dirs, mocker) -> None:

    ftp_folder, tty_file = tmp_dirs

    config: Config = {
        "frequency": 5.0,
        "tty": str(tty_file),
        "sleep": True,
        "start_sleep": "09:30",
        "stop_sleep": "18:00",
        "ftp_folder": str(ftp_folder),
        "wait_ftp": True,
        "override_sleep_blocked": True,
    }

    def _started_sleep(tty_file: Path) -> bool:
        content = _read_file_content(tty_file)
        if content is None:
            return False
        if "sleep:" in content:
            return True
        return False

    def _now_is_11am() -> datetime.time:
        return datetime.time(11, 0, 0)

    mocked_datetime_now = mocker.patch(
        "nightskycam.sleepypi.runner._now", side_effect=_now_is_11am
    )

    ftp_file = ftp_folder / "test.npy"
    ftp_file.touch()

    with get_manager((SleepyPiRunner, config)):
        # running an in stance of SpaceKeeperRunner
        wait_for(runner_started, True, args=(SleepyPiRunner.__name__,))
        wait_for_status(SleepyPiRunner.__name__, State.running, timeout=2.0)
        wait_for(lambda: mocked_datetime_now.call_count > 0, True)
        exception_on_error_state(SleepyPiRunner.__name__)
        assert _read_file_content(tty_file) is None
        ftp_file.unlink()
        wait_for(_started_sleep, True, args=(tty_file,))
        exception_on_error_state(SleepyPiRunner.__name__)
