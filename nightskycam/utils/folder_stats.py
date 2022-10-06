from pathlib import Path
import shutil
import math
import typing
import os


def convert_size(size_bytes: int) -> str:
    if size_bytes == 0:
        return "0B"
    size_name = ("B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    return "%s %s" % (s, size_name[i])


def list_nb_files(path: Path) -> typing.Dict[str, int]:

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
    return sum(os.path.getsize(f) for f in os.listdir(str(path)) if os.path.isfile(f))


def disk_stats() -> str:
    total_, used_, free_ = shutil.disk_usage("/")
    total = convert_size(total_)
    used = convert_size(used_)
    free = convert_size(free_)
    return f"disk size: {total} | used: {used} | free: {free}"
