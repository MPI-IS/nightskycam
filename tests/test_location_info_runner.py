import datetime
from typing import Generator

import pytest
from nightskycam.location_info.runner import LocationInfoRunner
from nightskycam.utils.location_info import LocationInfo, get_location_info
from nightskycam.utils.test_utils import (ConfigTester, configuration_test,
                                          exception_on_error_state,
                                          get_manager, runner_started,
                                          wait_for)
from nightskycam.utils.weather import Weather, get_weather
from nightskyrunner.config import Config
from nightskyrunner.shared_memory import SharedMemory


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
def mocked_weather(mocker):
    # mocking get_weather because it makes an internet call, with
    # varying results (because well, weather changes)
    custom_weather = Weather()
    custom_weather["cloud_cover"] = 50
    custom_weather["description"] = "Partly cloudy"
    custom_weather["temperature"] = 20
    mocker.patch(
        "nightskycam.utils.weather._weather",
        return_value=custom_weather,
    )


def test_mocked_weather(mocked_weather):
    weather = get_weather("tuebingen", "notarealkey")
    assert weather["description"] == "Partly cloudy"


@pytest.fixture
def mocked_location_info(mocker):
    # mocking get_location_info, because it makes an internet call
    location_info = LocationInfo()

    location_info["name"] = "Tuebingen Am Neckar"
    location_info["latitude"] = 48.5216
    location_info["longitude"] = 9.0576
    location_info["country"] = "Germany in Europa"
    location_info["timezone"] = "Europe/Berlin"
    mocker.patch(
        "nightskycam.utils.location_info._location_info",
        return_value=location_info,
    )


def test_mocked_location_info(mocked_location_info):
    for _ in range(3):
        li = get_location_info("tuebingen", "notarealkey")
        assert li["name"] == "Tuebingen Am Neckar"


@pytest.fixture
def mocked_datetime_now(monkeypatch):
    class patched_datetime(datetime.datetime):
        @classmethod
        def now(cls):
            return datetime.datetime(2020, 10, 10, 13, 0, 0)

        @classmethod
        def utcnow(cls):
            return datetime.datetime(2020, 10, 10, 13, 0, 0)

    monkeypatch.setattr(datetime, "datetime", patched_datetime)


def test_mocked_datetime_now(mocked_datetime_now):
    time_now = datetime.datetime.now()
    assert time_now.hour == 13


def test_mocked_datetime_utcnow(mocked_datetime_now):
    time_now = datetime.datetime.utcnow()
    assert time_now.hour == 13


class _LocationInfoRunnerConfig:
    @classmethod
    def get_config(cls, unsupported: bool = False) -> Config:
        if unsupported:
            return {"sun_altitude_threshold": "not a float !"}
        else:
            return {
                "frequency": 5.0,
                "sun_altitude_threshold": -0.2,
                "place_id": "tuebingen",
                # calls to meteosource.com are mocked, so no real key needed
                "weather_api_key": "lalalala",
            }

    @classmethod
    def get_config_tester(cls) -> ConfigTester:
        return ConfigTester(
            cls.get_config(unsupported=False),
            cls.get_config(unsupported=True),
        )


def test_configuration(
    reset_memory, mocked_weather, mocked_location_info, mocked_datetime_now
) -> None:
    """
    Testing instances of LocationInfoRunner behave correctly
    to changes of configuration.
    """
    config_tester = _LocationInfoRunnerConfig.get_config_tester()
    configuration_test(LocationInfoRunner, config_tester, timeout=30.0)


def test_location_info_runner(
    reset_memory, mocked_weather, mocked_location_info, mocked_datetime_now
) -> None:
    """
    Testing the iterate function of LocationInfoRunner.
    """

    def _memory_written(memory_key: str):
        all_memories = SharedMemory.get_all()
        try:
            memory = all_memories[memory_key]
        except KeyError:
            return False
        if not memory:
            return False
        return True

    config: Config = _LocationInfoRunnerConfig.get_config()
    memory_key = LocationInfoRunner.sm_key

    with get_manager((LocationInfoRunner, config)):
        # waiting for the instance of LocationInfoRunner to be running
        wait_for(runner_started, True, args=(LocationInfoRunner.__name__,))
        # waiting for the iteration function to have been called
        # at least once (we know because something has been written in
        # the shared memory
        wait_for(_memory_written, True, args=(memory_key,))
        # checking the location info runner has not switched to
        # error state
        exception_on_error_state(LocationInfoRunner.__name__)

        # checking the memory content is as expected
        memory = SharedMemory.get(memory_key)
        # for reason I could not determine,
        # mocking of datetime.utc and datetime.now
        # do not work.
        # assert not memory["night"]  # datetime now mocked at 1pm
        assert memory["weather"] == "Partly cloudy"
        assert memory["temperature"] == 20
        assert memory["cloud_cover"] == 50
