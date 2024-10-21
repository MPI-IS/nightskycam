"""
Module defining LocationInfoRunner.
"""

from contextlib import suppress
import subprocess
import time
from datetime import datetime
from typing import List, Optional

from nightskycam.utils.location_info import LocationInfo, get_location_info
from nightskycam.utils.night import is_night
from nightskycam.utils.weather import Weather, get_weather
from nightskycam_serialization.status import LocationInfoRunnerEntries
from nightskyrunner.config_getter import ConfigGetter
from nightskyrunner.runner import ThreadRunner, status_error
from nightskyrunner.shared_memory import SharedMemory
from nightskyrunner.status import Level
from nightskyrunner.wait_interrupts import RunnerWaitInterruptors

from .ip import get_IPs


# must be the same value as in nightskycam_images.constants.TIME_FORMAT
TIME_FORMAT: str = "%H:%M:%S"


@status_error
class LocationInfoRunner(ThreadRunner):
    sm_key = "forecast"
    """
    An instance of Forecast will write a dictionary
    in the shared memory under this key
    Runner that fetch from [meteosource](https://www.meteosource.com)
    information regarding the location of the system.
    It also determines using [ephem](https://rhodesmill.org/pyephem/)
    if it is currenttly night time.
    The information is written in the shared memory under the key
    [LocationInfoRunner.sm_key](). These values are written in the
    shared memory dictionary:

    - night (True means currently night time)
    - weather: current weather description (e.g. 'rainy')
    - temperature: in degree celcius
    - cloud cover: in percentage, 0% meaning no clouds at all over the area
    - time stamp: machine time the data was written in the shared memory

    The value of the data written in the shared memory is updated every:

    - at most once per [nightskycam.utils.weather.WEATHER_UPDATE_PERIOD][] 
      minutes for the weather
    - at most once per [nightskycam.utils.night.NIGHT_UPDATE_PERIOD minutes 
      for the day/night status

    The required configuration keys are:

    - place_id: the location of the system, as supported by meteosource.
      See: [meteosource](https://www.meteosource.com/documentation#find_places)
    - weather_api_key:
      see [meteosource pricing](https://www.meteosource.com/pricing)
      (a free key will be enough)

    An optional configuration key is:
    - sun_altitude_threshold: the sun altitude below which it will be
      considered to be night time (in radian).
      If not provided, a default value of -0.1 is used.

    This runner also writes the introspection key "outside_temperature",
    corresponding to outside temperature at the location of the system
    (as provided by meteosource.com).
    See [nightskycam.introspection.IntrospectionRunner](IntrospectionRunner)

    All the information is also shared with the world via the status of this
    runner. The status is also updated with the network IP information of
    the device and the local time at the place_id.
    """

    """
    Runner that fetch from [meteosource](https://www.meteosource.com)
    information regarding the location of the system.
    It also determines using [ephem](https://rhodesmill.org/pyephem/)
    if it is currenttly night time.
    The information is written in the shared memory under the key
    [LocationInfoRunner.sm_key](). These values are written in the
    shared memory dictionary:

    - night (True means currently night time)
    - weather: current weather description (e.g. 'rainy')
    - temperature: in degree celcius
    - cloud cover: in percentage, 0% meaning no clouds at all over the area
    - time stamp: machine time when the data was written in the shared memory

    Even when the data is written in the shared memory at a high frequency,
    it is not updated at the same frequency. Weather is queried online at most
    once per 30 minutes, and sun altitude once per 15 minutes.

    The required configuration keys are:

    - place_id: the location of the system, as supported by meteosource.
      See: [meteosource](https://www.meteosource.com/documentation#find_places)
    - weather_api_key:
      see [meteosource pricing](https://www.meteosource.com/pricing)
      (a free key will be enough)

    An optional configuration key is:
    - sun_altitude_threshold: the sun altitude below which it will be
      considered to be night time (in radian).
      If not provided, a default value of -0.1 is used.

    All the information is also shared with the world via the status of this
    runner. The status is also updated with the network IP information of
    the device and the local time at the place_id.
    """

    def __init__(
        self,
        name: str,
        config_getter: ConfigGetter,
        interrupts: RunnerWaitInterruptors = [],
        core_frequency: float = 1.0 / 0.005,
    ) -> None:
        super().__init__(name, config_getter, interrupts, core_frequency)
        SharedMemory.get(self.sm_key)

    def iterate(self) -> None:
        utc_time = datetime.utcnow()
        config = self.get_config()
        place_id = str(config["place_id"])
        api_key = str(config["weather_api_key"])
        try:
            sun_alt_threshold = float(
                config["sun_altitude_threshold"]  # type: ignore
            )
        except KeyError:
            sun_alt_threshold = -0.1

        # creating an empty location then filling it
        # with information
        location = LocationInfoRunnerEntries()

        # for tracking all errors
        errors: List[str] = []

        # reading the temperature of the cpu
        try:
            command = "cat /sys/class/thermal/thermal_zone0/temp"
            output = subprocess.run(command, capture_output=True, shell=True)
            location["cpu_temperature"] = str(
                float(output.stdout.decode("utf-8")) / 1000.0
            )
        except Exception as e:
            errors.append(f"failed to read the temperature of the CPU: {e}")

        # sun altitude threshold (to decide based on the
        # current sun altitude if it is day or night)
        location["sun_alt_threshold"] = sun_alt_threshold

        # weather information (temperature, cloud coverage)
        try:
            weather: Optional[Weather] = get_weather(place_id, api_key)
            if weather:
                location["cloud_cover"] = weather["cloud_cover"]
                location["weather"] = weather["description"]
                location["temperature"] = weather["temperature"]
        except Exception as e:
            errors.append(
                f"{type(e)}: failed to determine "
                f"current weather at {place_id} ({e})"
            )

        # latitude, longitude, country, timezone
        info: Optional[LocationInfo]
        try:
            info = get_location_info(place_id, api_key)
            if info:
                location["latitude"] = info["latitude"]
                location["longitude"] = info["longitude"]
                location["name"] = info["name"]
                location["country"] = info["country"]
                location["timezone"] = info["timezone"]
        except Exception as e:
            errors.append(
                f"{type(e)}: failed to read info related to {place_id} ({e})"
            )

        # what is the current sun altitude ? is it night time ?
        if info:
            try:
                night, sun_alt = is_night(
                    float(info["latitude"]),
                    float(info["longitude"]),
                    utc_time,
                    threshold=sun_alt_threshold,
                )
                location["night"] = night
                location["sun_alt"] = sun_alt
            except Exception as e:
                errors.append(
                    f"{type(e)}: failed to determine if night time: {e}"
                )

        # network IP(s) of the system
        location["IPs"] = ", ".join(
            [ip for ip in get_IPs() if "127.0.0.1" not in ip]
        )

        # local time
        location["local_time"] = datetime.now().strftime(TIME_FORMAT)

        # if there has been any error while fetching data,
        # informing the world via a status issue
        if errors:
            error_message = ", ".join(errors)

            self._status.set_issue(error_message)
            for error in errors:
                self.log(Level.warning, error)
        else:
            self._status.remove_issue()

        # sharing the status
        self._status.entries(location)

        # sharing the information in the shared memory
        # The CamRunner will read this information to
        # "decide" if picture should be taken
        # (e.g. if night is False, picture will not be taken).
        memory = SharedMemory.get(self.sm_key)
        for key in ("night", "weather", "temperature", "cloud_cover"):
            with suppress(KeyError):
                memory[key] = location[key]
        memory["time_stamp"] = time.time()
