"""
Utility functions for
[nightskycam.space_keeper.runner.SpaceKeeperRunner](space keeper runner).
"""

from typing import TypedDict
import os
from pathlib import Path
from typing import Dict, List, Tuple

import psutil

from ..utils.formating import bits_to_human

_BITS_PER_BYTE = 8


def folder_content(path: Path) -> Tuple[Dict[str, int], int]:
    """
    Arguments:
    path: absolute path of the folder to investigate

    Returns:
    Tuple of a dict and an int:
    - the dict has for keys a file extension (e.g. 'jpeg') and as
      values the number of files with this extension
    - the int is the total size of the content of this folder (recursive)
    """
    if not path.is_dir():
        path.mkdir(parents=True)

    extension_count: Dict[str, int] = {}
    total_size_bits: int = 0

    for file_path in path.iterdir():
        if file_path.is_file():
            extension = file_path.suffix  # Get the file extension
            total_size_bits += (
                file_path.stat().st_size * _BITS_PER_BYTE
            )  # Convert to bits

            if extension in extension_count:
                extension_count[extension] += 1
            else:
                extension_count[extension] = 1

    return extension_count, total_size_bits


def convert_mb_to_bits(mb: int) -> int:
    """
    Convert MB to bits.
    """
    return mb * _BITS_PER_BYTE * 1024 * 1024


_root_folder = Path("/")


class DiskSpaceInfo(TypedDict):
    total_space: int
    free_space: int
    used_space: int
    percent_used: float


def disk_space_info(path: Path = _root_folder) -> DiskSpaceInfo:
    """
    Returns a dict providing information related to the disk
    mounting "path"
    """

    disk_usage = psutil.disk_usage(str(path))
    return {
        "total_space": disk_usage.total * _BITS_PER_BYTE,
        "free_space": disk_usage.free * _BITS_PER_BYTE,
        "used_space": disk_usage.used * _BITS_PER_BYTE,
        "percent_used": float(disk_usage.percent),
    }


def disk_space_info_str(dsi: DiskSpaceInfo) -> str:
    return str(
        f"{bits_to_human(dsi['total_space'] * _BITS_PER_BYTE)} "
        f"- free: {dsi['percent_used']}% ({bits_to_human(dsi['free_space'] * _BITS_PER_BYTE)})"
    )


def to_GB(space: str) -> float:
    """
    Convert a disk space in the format "<number>KB" or "<number>MB"
    or "<number>GB" to a size in GB.
    """
    units = {"KB": 0.0009765625**2, "MB": 0.0009765625, "GB": 1.0}
    if len(space) < 3:
        raise ValueError(
            f"Can not convert {space} to gigabytes: "
            f"only {','.join(list(units.keys()))} supported"
        )
    number, unit = space[:-2], space[-2:]
    if unit not in units.keys():
        raise ValueError(
            f"Can not convert {space} to gigabytes: "
            f"only {','.join(list(units.keys()))} supported"
        )
    size = float(number)
    size_in_gb = size * units[unit]
    return size_in_gb


def _free_space() -> int:
    return psutil.disk_usage("/").free


def free_space() -> int:
    """
    Returns the free space of the top root directory (in bits)
    """
    # calling _free_space rather than psutil because of
    # the mocking of this function in test_space_keeper_runner.py.
    # For some reason, patching free_space does not work, but
    # patching _free_space does. I suspect it is because
    # free_space is directly imported in test_space_keeper_runner.py
    # while _free_space is not.
    return _free_space()


def file_size(filepath: Path) -> int:
    """
    Returns the size of the file (in bits)
    """
    return filepath.stat().st_size * _BITS_PER_BYTE


def files_to_delete(folder: Path, threshold: int) -> List[Path]:
    """
    If the available space is below the given threshold, returns a list
    of the oldest files located in folder (not recursive) that would need
    to be deleted in order to get the available space back above the threshold
    (returns an empty list otherwise)
    """
    fs = free_space()

    # nothing to delete if enough free space
    if fs >= threshold:
        return []

    # files should be deleted ! Selecting the oldest files.
    files = [item for item in folder.iterdir() if item.is_file()]
    files.sort(key=lambda file_: os.path.getmtime(str(file_)))
    index = 0
    total_size = 0
    r: List[Path] = []
    to_delete = threshold - fs
    while index < len(files) and total_size < to_delete:
        total_size += file_size(files[index])
        r.append(files[index])
        index += 1
    return r
