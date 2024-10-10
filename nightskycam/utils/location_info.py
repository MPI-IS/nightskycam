"""
Module defining get_location_info, which fetches from meteosource
information related to a place id (place id: identifier used
by meteosource, see
[meteosource](https://www.meteosource.com/client/interactive-documentation#/Location%20endpoints).
"""

from typing import Dict, Optional, TypedDict

import requests

_url = "https://www.meteosource.com/api/v1/free/find_places"


class LocationInfo(TypedDict):
    latitude: float
    longitude: float
    name: str
    country: str
    timezone: str


def _read_coord(coord: str) -> float:
    # latitude and longitude input are expected
    # to be in format such as:
    # "13N" or "23S" or "12W" or "12E".
    # Returns the corresponding float value,

    # in N/E convension
    # i.e. 13N -> 13, 13S -> -13,
    # 23W -> -23, 23E -> 23

    direction = coord[-1].lower()
    value = float(coord[:-1])
    if direction in ("n", "s"):
        if direction == "s":
            return -value
        return value
    if direction in ("w", "e"):
        if direction == "w":
            return -value
        return value
    raise ValueError(
        f"can not convert longitude/latitude {coord}: direction should be in N,S,W,E"
    )


def _location_info(place_id: str, api_key: str) -> Optional[LocationInfo]:
    # Query meteosource to get information regarding weather and
    # longitude/latitude coordinates.

    parameters = {
        "key": api_key,
        "text": place_id,
    }
    data = requests.get(_url, parameters).json()
    for d in data:
        if d["place_id"] == place_id:
            info = LocationInfo(
                name=d["name"],
                latitude=_read_coord(d["lat"]),
                longitude=_read_coord(d["lon"]),
                country=d["country"],
                timezone=d["timezone"],
            )
            return info
    return None


_known_locations: Dict[str, LocationInfo] = {}
"""
Caching of instances of LocationInfo (key: place_id, value: instance of LocationInfo)
"""


def get_location_info(place_id: str, api_key: str) -> Optional[LocationInfo]:
    """
    Fetch from meteosource the latitude, longitude, name, country and timezone
    of the place id. Cache the results, so the fetching will be done once per
    place_id

    Arguments:
      place_id: see [meteosource](https://www.meteosource.com/client/interactive-documentation#/Location%20endpoints)
      api_key: see [meteosource pricing](https://www.meteosource.com/pricing) (a free key should be enough)
    """
    global _known_locations
    try:
        return _known_locations[place_id]
    except KeyError:
        li: Optional[LocationInfo] = _location_info(place_id, api_key)
        if li is not None:
            _known_locations[place_id] = li
        return li
