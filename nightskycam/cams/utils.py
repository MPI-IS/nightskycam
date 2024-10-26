"""
Module for the read_config, is_active and get_local_info 
functions used by CamRunner.
"""

import datetime
import time
from datetime import datetime as dtime
from typing import Optional, Tuple

from nightskyrunner.config import Config
from nightskyrunner.shared_memory import SharedMemory

from ..location_info.runner import LocationInfoRunner


def _to_time(config_time: str) -> Optional[datetime.time]:
    # Cast config_time to datetime.time.
    # config_time is expected in format "HOUR:MINUTE".

    if config_time == "None":
        return None
    return dtime.strptime(config_time, "%H:%M").time()


def _period_active(
    start: Optional[datetime.time],
    end: Optional[datetime.time],
    time_now: datetime.time,
) -> bool:
    """
    start being a time from which camera activity should start
    and stop a time at which it should stop, returns True
    if the current time is in the activity interval.
    Returns also True if either start or end is None.
    """

    if start is None:
        return True
    if end is None:
        return True
    if end < start:
        # end record: next day
        if time_now > start or time_now < end:
            return True
    else:
        # end record: same day
        if time_now > start and time_now < end:
            return True
    return False


def time_window_str(
    start: Optional[datetime.time], end: Optional[datetime.time]
) -> str:
    """
    Returns the interval start-end in a friendly formatted string.
    """
    if start is None or end is None:
        return "always"
    return f"{start.strftime('%H:%M')} - {end.strftime('%H:%M')}"


def read_config(
    config: Config,
) -> Tuple[
    Optional[datetime.time],
    Optional[datetime.time],
    bool,
    bool,
    Optional[int],
    str,
    float,
    bool,
]:
    """
    Parse the configuration.
    Expected keys:

    - start_time (formatted: "%H:%M")
    - end_time (formatted: "%H:%M")
    - use_sun_alt (bool)
    - use_weather (bool)
    - cloud_cover_threshold (int between 0 and 100)
    - system_name (str)
    - frequency (positive float)
    - pause (bool)
    """

    start = _to_time(str(config["start_time"]))
    end = _to_time(str(config["end_time"]))
    use_sun_alt = config["use_sun_alt"]
    use_weather = config["use_weather"]

    if not type(use_sun_alt) == bool:
        raise TypeError(
            f"configuration for use_sun_alt should be a boolean, got {use_sun_alt} ({type(use_sun_alt)}) instead"
        )

    if not type(use_weather) == bool:
        raise TypeError(
            f"configuration for use_weather should be a boolean, got {use_weather} ({type(use_weather)}) instead"
        )

    if use_weather:
        cloud_cover_threshold = int(
            config["cloud_cover_threshold"]  # type: ignore
        )  # type: ignore
    else:
        cloud_cover_threshold = None
    system_name = str(config["nightskycam"])
    frequency = float(config["frequency"])  # type: ignore

    pause: bool = False
    try:
        pause = config["pause"]  # type: ignore
    except KeyError:
        pass
    else:
        if not type(pause) == bool:
            raise TypeError(
                f"configuration for pause should be a boolean, got {pause}({type(pause)}) instead"
            )

    return (
        start,
        end,
        use_sun_alt,
        use_weather,
        cloud_cover_threshold,
        system_name,
        frequency,
        pause,
    )


def is_active(
    start: Optional[datetime.time],
    end: Optional[datetime.time],
    use_sun_alt: bool,
    use_weather: bool,
    night: Optional[bool],
    cloud_cover: Optional[int],
    cloud_cover_threshold: int,
    weather: Optional[str],
    time_now: datetime.time,
    pause: bool,
) -> Tuple[bool, str, bool]:
    """
    "Decides" based on the passed argument if pictures should be taken now.

    Will not take picture if:

    - use_weather is True and cloud_cover is above cloud_cover_threshold
    - use_sun_alt is True and night is False
    - use_sun_alt is False and time_now is not in the start - end interval
    - pause is True

    Returns:
      A tuple:

      - active: if True, pictures should be taken
      - reason: string giving insight on why active is True of False
      - bad_weather: if True, means active is False and the reason is
        bad weather (i.e. weather is True and cloud_cover is above
        cloud_cover_threshold).
    """

    # if pausing, no picture should be taken
    if pause:
        return False, "requested to pause", False

    # will be used to update "reason" with cloud cover information
    if use_weather and cloud_cover:
        if cloud_cover > cloud_cover_threshold:
            cloud_cover_str = f"cloud cover: {cloud_cover}% (above threshold of {cloud_cover_threshold}%)"
        else:
            cloud_cover_str = f"cloud cover: {cloud_cover}% (below threshold of {cloud_cover_threshold}%)"
    else:
        cloud_cover_str = ""

    if use_sun_alt and night is not None:
        if not night:
            # according to sun altitude it is daytime, so
            # no picture taken now.
            return False, "day time", False
        else:
            if use_weather and cloud_cover is not None:
                if cloud_cover > cloud_cover_threshold:
                    # it is night, but bad weather !
                    # no picture taken now
                    return (
                        False,
                        f"night time but cloudy - {cloud_cover_str}",
                        True,
                    )
                else:
                    # it is night and no cloud in the sky, taking
                    # pictures now
                    return (
                        True,
                        f"night time and suitable weather - {cloud_cover_str}",
                        False,
                    )
            else:
                # It is night and weather forecast is not used, taking picture.
                return True, "night time", False

    # sun altitude is not used, using the fixed activity window
    # (start / end interval)

    active_period = _period_active(start, end, time_now)
    period_str = time_window_str(start, end)

    if not active_period:
        # current time is not in the start / end interval, no
        # picture to be taken.
        return False, f"not in active period ({period_str})", False

    if use_weather and cloud_cover is not None:
        if cloud_cover > cloud_cover_threshold:
            # we are in the start / end interval, but weather is bad,
            # not taking picture.
            return (
                False,
                f"in active period ({period_str}) but cloudy - {cloud_cover_str}",
                True,
            )
        else:
            # we are in the start / end interval and nice weather, therefore taking pictures.
            return (
                True,
                f"in active period ({period_str}) and suitable weather - {cloud_cover_str}",
                False,
            )

    # in active period and weather forecast is not used, taking picture.
    return True, f"in active period ({period_str})", False


def get_local_info(
    deprecation=10 * 60, tnow: Optional[float] = None
) -> Tuple[Optional[bool], Optional[str], Optional[int]]:
    """
    Reads the shared memory written by [nighskycam.location_info.runner.LocalInfoRunner]() and
    returns the tuple:

    - night (bool): True if sun altitude below sun altitude threshold.
    - weather (str): description of the weather (e.g. 'cloudy').
    - cloud_cover (int): current cloud coverage of the area, 0 for clear, 100 for total cloud coverage.

    The tuple (None, None, None) will be returned if:
    - there is not data in the shared memory (likely: no instance of LocalInfoRunner is running)
    - the data in the shared memory is deprecated (one hour old by default, for some reason LocalInfoRunner
      is failing to write new data)

    Arguments:
      deprecation: duration in seconds after which the information written in the shared memory by
        an instance of LocalInfoRunner is considered deprecated
      tnow: current time (in seconds, a returned for example by time.time())
    """

    try:
        memory = SharedMemory.get(LocationInfoRunner.sm_key)
    except KeyError:
        return None, None, None
    if not memory:
        return None, None, None
    ts = memory["time_stamp"]
    if tnow is None:
        tnow = time.time()
    if tnow - ts > deprecation:
        return None, None, None
    try:
        return tuple(
            memory[key]  # type: ignore
            for key in ("night", "weather", "cloud_cover")
        )
    except KeyError:
        return None, None, None
