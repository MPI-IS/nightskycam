"""
Module defining the format_seconds function.
"""

from typing import Optional, Tuple


def _seconds_to_DHMS(duration: float) -> Tuple[int, int, int, int]:
    duration_ = int(duration + 0.5)
    m, s = divmod(duration_, 60)
    h, m = divmod(m, 60)
    d, h = divmod(h, 24)
    return (d, h, m, s)


def format_seconds(duration: Optional[float]) -> str:
    """
    Duration being in seconds, return a string giving the
    corresponding duration in terms of days, hours, minutes and
    seconds (or an empty string if duration is None).
    """
    if not duration:
        return ""
    d, h, m, s = _seconds_to_DHMS(duration)

    def _f(value: int, label: str) -> str:
        return str(value) + label + "" if value > 0 else ""

    return "".join(
        [
            _f(v, l)
            for v, l in zip(
                (d, h, m, s), (" days ", " hours ", " minutes ", " seconds")
            )
        ]
    )


def bits_to_human(bits: int) -> str:
    """
    Convert the number of bits to a human
    friendly string giving the size in
    KB, MB and GB.
    """
    bits_ = float(bits)
    kilobytes = bits_ / 8 / 1024
    if kilobytes < 1024:
        return f"{kilobytes:.2f} KB"
    megabytes = kilobytes / 1024
    if megabytes < 1024:
        return f"{megabytes:.2f} MB"
    gigabytes = megabytes / 1024
    return f"{gigabytes:.2f} GB"


def bytes_to_human(bytes_value):
    # Define conversion factors
    KB = 1024
    MB = KB * 1024
    GB = MB * 1024
    TB = GB * 1024

    # Determine the appropriate unit
    if bytes_value >= TB:
        value = bytes_value / TB
        unit = "TB"
    elif bytes_value >= GB:
        value = bytes_value / GB
        unit = "GB"
    elif bytes_value >= MB:
        value = bytes_value / MB
        unit = "MB"
    else:
        value = bytes_value / KB
        unit = "KB"

    # Format the output
    return f"{value:.2f} {unit}"
