"""
Module defining the get_weather method, which fetches weather
information online.
"""

from typing import TypedDict

import requests
from cachetools import TTLCache, cached

_url = "https://www.meteosource.com/api/v1/free/point"


class Weather(TypedDict):
    """
    Holder for weather related information
    """

    cloud_cover: int
    description: str
    temperature: int


class WeatherError(Exception):
    """
    To be raised when there has been an error when
    fetching online weather information.
    """

    ...


def _weather(place_id: str, api_key: str) -> Weather:
    parameters = {
        "key": api_key,
        "place_id": place_id,
    }
    data = requests.get(_url, parameters).json()
    try:
        current = data["current"]
    except KeyError:
        raise WeatherError(data["detail"])
    w = Weather(
        cloud_cover=int(current["cloud_cover"]),
        description=current["summary"],
        temperature=current["temperature"],
    )
    return w


WEATHER_UPDATE_PERIOD = 30
"""How often the weather will be fetched from internet (in minutes)"""


@cached(cache=TTLCache(maxsize=1, ttl=WEATHER_UPDATE_PERIOD * 60))
def get_weather(place_id: str, api_key: str) -> Weather:
    """
    Fetch weather information related to the place id from
    meteosource.com.
    Weather information will not be fetched at each call: it will
    be fetched at most one time per 30 minutes. Calls made in the
    meantime will return cached information.

    Arguments:
    - place_id: must be supported by meteosource.com. See:
      [meteosource documentation](https://www.meteosource.com/client/interactive-documentation#/Location%20endpoints)
    - api_key: you may get a free one (400 calls per day) [here](https://www.meteosource.com/pricing)

    Raises:
    - A [WeatherError]() if fetching of weather data fails for any reason.
    """
    return _weather(place_id, api_key)
