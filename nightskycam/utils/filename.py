"""
Module for generating / parsing file names based
on the current host name and the current date and time.
"""

from datetime import datetime
from datetime import time as dtime
from datetime import timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

_format = "%Y_%m_%d_%H_%M_%S"
_day_format = "%Y_%m_%d"


def get_filename(
    system_name: str,
    date: Optional[datetime] = None,
) -> str:
    """
    returns system_name_current_date_and_time
    If the date is None, the current time is used.
    """
    if date is None:
        date = datetime.now()
    date_ = date.strftime(_format)
    filename = f"{system_name}_{date_}"
    return filename


def get_date(filename: Union[str, Path]) -> datetime:
    """
    Assuming the filename has been created via the
    [nightskycam.utils.filename.get_filename][get_filename]
    method, returns the corresponding date.
    """
    if isinstance(filename, Path):
        fname = filename.stem
    else:
        fname = filename
    first_index = fname.index("_")
    if fname.count("_") == (_format.count("_") + 1):
        return datetime.strptime(fname[first_index + 1 :], _format)
    second_index = fname.index("_", first_index + 1)
    return datetime.strptime(fname[second_index + 1 :], _format)


def is_date_filename(filename: Union[str, Path]) -> bool:
    """
    Returns True if the filename matches a file created
    via the [nightskycam.utils.filename.get_filename][get_filename]
    method
    """
    if isinstance(filename, Path):
        fname = filename.stem
    else:
        fname = filename
    fcount = _format.count("_")
    if fname.count("_") not in (fcount + 1, fcount + 2):
        return False
    return True


def _is_morning(d: datetime) -> bool:
    """
    Returns True if d is between midnight
    and noon.
    """
    noon = dtime(hour=12, minute=0)
    return d.time() < noon


def _night_date(d: datetime) -> datetime:
    """
    Returns d stripped from hour, minute, second and microsecond,
    and remove one day from d if morning.
    """
    if _is_morning(d):
        d = d - timedelta(days=1)
    return d.replace(hour=0, minute=0, second=0, microsecond=0)


def sort_by_night(folder: Path) -> List[Tuple[str, List[Tuple[dtime, Path]]]]:
    """
    Read all files of which names are "date" formated, group them by sorted night date.
    E.g.

    ```python
    [
      ("12_06_2034", [ (dtime1, Path1) , (dtime2, Path2 ] ),
      ("11_06_2034", [ (dtime3, Path3) ] )
    ]
    ```

    means the folder has three files, two files corresponding to June 12th 2034
    and one corresponding to June 11th 2034.

    Note files are ordered newest first.
    """
    dates_ = [
        (
            _night_date(get_date(f)),
            get_date(f).time(),
            f,
        )
        for f in folder.glob("*")
        if f.is_file() and is_date_filename(f)
    ]
    dates: Dict[datetime, List[Tuple[dtime, Path]]] = {}
    for night_date, ftime, f in dates_:
        try:
            dates[night_date].append((ftime, f))
        except KeyError:
            dates[night_date] = [(ftime, f)]
    sorted_dates: List[Tuple[str, List[Tuple[dtime, Path]]]] = [
        (
            key.strftime(_day_format),
            sorted(dates[key], key=lambda t_p: t_p[0], reverse=True),
        )
        for key in sorted(dates.keys(), reverse=True)
    ]
    return sorted_dates
