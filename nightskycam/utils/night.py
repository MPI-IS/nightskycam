"""
Module defining the 'is_night' method, which 
determines if it is currently night at a given location
(using the [ephem](https://rhodesmill.org/pyephem/) package).
"""

import math
from datetime import datetime
from typing import Tuple

import ephem
from cachetools import TTLCache, cached

NIGHT_UPDATE_PERIOD = 15
"""How often the day/night status will be evaluated (in minutes)"""


@cached(cache=TTLCache(maxsize=1000, ttl=NIGHT_UPDATE_PERIOD * 60))
def is_night(
    latitude: float,
    longitude: float,
    utc_time: datetime,
    threshold: float = -0.1,
) -> Tuple[bool, float]:
    """
    Determine if it is night at the provided time and location, based
    on the current sun altitude and threshold.
    It computes its output at most one per 15 minutes. Calls made in
    the meatime will return cached values.

    Arguments:
    - latitude: in degrees
    - longitude: in degrees
    - utc_time
    - threshold: night if the sun altitude is below this threshold

    Returns:
    - night and the sun altitude
    """

    latitude_, longitude_ = math.radians(latitude), math.radians(longitude)
    observer = ephem.Observer()
    observer.long = float(longitude_)
    observer.lat = float(latitude_)
    observer.date = utc_time
    sun = ephem.Sun()
    sun.compute(observer)
    return sun.alt < threshold, float(repr(sun.alt))
