"""
Module defining functions for monitoring the size of disks and folders.
"""

import math
import os
import shutil
import typing
from pathlib import Path


def convert_size(size_bytes: int) -> str:
    """
    Convert a size in bytes to a friendly string,
    e.g. "1.5MB"
    """
    if size_bytes == 0:
        return "0B"
    size_name = ("B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    return "%s %s" % (s, size_name[i])


def list_nb_files(path: Path) -> typing.Dict[str, int]:
    """
    Count the files contained in "path" (non recursive), grouped
    by extensions. E.g. {"npy":3, "toml:2"} means "path" contains
    3 npy files and 2 toml files.
    """

    files = list(filter(lambda x: x.is_file(), path.glob("*")))

    r: typing.Dict[str, int] = {}

    for f in [str(f_) for f_ in files]:
        try:
            index_point = f.rindex(".")
        except ValueError:
            try:
                r["no extension"] += 1
            except KeyError:
                r["no extension"] = 1
        else:
            try:
                r[f[index_point + 1 :]] += 1
            except KeyError:
                r[f[index_point + 1 :]] = 1

    return r


def folder_size(path: Path) -> int:
    """
    Return the size of the folder.
    """
    folder = str(path)
    return sum(
        os.path.getsize(folder + os.sep + f)
        for f in os.listdir(folder)
        if os.path.isfile(folder + os.sep + f)
    )


def disk_stats() -> str:
    """
    Return a string informing the user of the current
    disk usage (total size, used space and free space).
    """
    total_, used_, free_ = shutil.disk_usage("/")
    total = convert_size(total_)
    used = convert_size(used_)
    free = convert_size(free_)
    return f"disk size: {total} | used: {used} | free: {free}"
