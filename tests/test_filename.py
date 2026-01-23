import random
import tempfile
from datetime import datetime
from pathlib import Path

from nightskycam.utils.filename import (_day_format, _is_morning, _night_date,
                                        get_date, get_filename,
                                        is_date_filename, sort_by_night)


def test_dated_filename():
    """
    Testing get_filename, get_date and is_date_filename functions.
    """
    system_name = "test_nightskycam"

    filename = get_filename(system_name)

    assert system_name in filename
    assert is_date_filename(filename)

    date1 = get_date(filename)

    filename = get_filename(system_name)

    date2 = get_date(filename)

    assert (date2 - date1).total_seconds() < 0.5

    filename = "not_a_filename"
    assert not is_date_filename(filename)

    date = datetime(year=2021, month=4, day=3, minute=34, second=56)
    filename = get_filename(system_name, date=date)
    out_date = get_date(filename)
    assert out_date == date


def test_is_morning():
    """
    Testing the _is_morning function.
    """
    morning = (
        datetime(year=2012, month=8, day=4, hour=1, minute=45, second=32),
        datetime(year=2025, month=8, day=4, hour=11, minute=13, second=32),
        datetime(year=2120, month=4, day=27, hour=10, minute=4, second=55),
    )
    for m in morning:
        assert _is_morning(m)

    not_morning = (
        datetime(year=2012, month=8, day=4, hour=12, minute=45, second=32),
        datetime(year=2025, month=8, day=4, hour=23, minute=13, second=32),
        datetime(year=2120, month=4, day=27, hour=16, minute=4, second=55),
    )
    for m in not_morning:
        assert not _is_morning(m)


def test_night_date():
    """
    Testing the _night_date function
    """
    p1 = datetime(year=2023, month=3, day=3, hour=16, minute=43, second=18)
    p2 = datetime(year=2023, month=3, day=3, hour=22, minute=16, second=45)
    p3 = datetime(year=2023, month=3, day=4, hour=2, minute=25, second=32)
    p4 = datetime(year=2023, month=3, day=4, hour=11, minute=27, second=58)
    night = datetime(year=2023, month=3, day=3)
    for p in (p1, p2, p3, p4):
        assert _night_date(p) == night


def test_sort_by_night():
    system_name = "test_nightskycam"

    ref_night1 = datetime(year=2023, month=3, day=3).strftime(_day_format)
    night1 = (
        datetime(year=2023, month=3, day=3, hour=16, minute=43, second=18),
        datetime(year=2023, month=3, day=3, hour=22, minute=16, second=45),
        datetime(year=2023, month=3, day=4, hour=2, minute=25, second=32),
        datetime(year=2023, month=3, day=4, hour=11, minute=27, second=58),
    )
    ref_night2 = datetime(year=2023, month=3, day=4).strftime(_day_format)
    night2 = (
        datetime(year=2023, month=3, day=4, hour=16, minute=44, second=18),
        datetime(year=2023, month=3, day=4, hour=22, minute=12, second=45),
        datetime(year=2023, month=3, day=5, hour=2, minute=21, second=32),
        datetime(year=2023, month=3, day=5, hour=11, minute=22, second=58),
    )

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(str(tmp))
        all_nights = list(night1) + list(night2)
        random.shuffle(all_nights)
        for date in all_nights:
            filename = get_filename(system_name, date=date)
            with open(tmp_dir / f"{filename}.jpeg", "w") as f:
                f.write(str(date))
            with open(tmp_dir / f"{filename}.toml", "w") as f:
                f.write(str(date))

        sorted_files = sort_by_night(tmp_dir)

    dates = [sf[0] for sf in sorted_files]

    assert set(dates) == set((ref_night1, ref_night2))

    def _assert_ordered(values: list) -> None:
        assert values[0] > values[-1]
        for v1, v2 in zip(values, values[1:]):
            assert v1 >= v2

    for ref_night, night in zip((ref_night1, ref_night2), (night1, night2)):
        dtime_path = [sf[1] for sf in sorted_files if sf[0] == ref_night][0]
        assert len(dtime_path) == len(night) * 2
        dtimes = [dp[0] for dp in dtime_path]
        _assert_ordered(dtimes)
