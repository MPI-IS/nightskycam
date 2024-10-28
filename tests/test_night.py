"""
Unit tests for the [nightskycam.utils.night]() module.
"""

from datetime import datetime

from nightskycam.utils.location_info import _read_coord
from nightskycam.utils.night import is_night


class _Tuebingen:
    latitude = _read_coord("48.5216N")
    longitude = _read_coord("9.0576E")


def _today_at_1pm() -> datetime:
    today = datetime.now().date()
    today_at_1pm = datetime(year=today.year, month=today.month, day=today.day, hour=13)
    return today_at_1pm


def _today_at_11pm() -> datetime:
    today = datetime.now().date()
    today_at_11pm = datetime(year=today.year, month=today.month, day=today.day, hour=23)
    return today_at_11pm


def test_is_day() -> None:
    """
    Test 'is_night' returns day for day time
    """
    night, sun_alt = is_night(
        latitude=_Tuebingen.latitude,
        longitude=_Tuebingen.longitude,
        utc_time=_today_at_1pm(),
        threshold=-0.1,
    )
    assert not night
    assert sun_alt > 0.1


def test_is_night() -> None:
    """
    Test 'is_night' returns night for night time
    """
    night, sun_alt = is_night(
        latitude=_Tuebingen.latitude,
        longitude=_Tuebingen.longitude,
        utc_time=_today_at_11pm(),
        threshold=-0.1,
    )
    assert night
    assert sun_alt < -0.1
