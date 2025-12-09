import pytest

from nightskycam.utils.location_info import _read_coord


def test_read_coord():
    latitude, longitude = "28.69503N", "17.85287W"
    assert _read_coord(latitude) == 28.69503
    assert _read_coord(longitude) == -17.85287

    latitude, longitude = "47.73333N", "8.06667E"
    assert _read_coord(latitude) == 47.73333
    assert _read_coord(longitude) == 8.06667

    latitude, longitude = "47.73333S", "8.06667E"
    assert _read_coord(latitude) == -47.73333
    assert _read_coord(longitude) == 8.06667

    with pytest.raises(ValueError):
        # 'G' is not a valid direction
        _read_coord("47.7333G")
