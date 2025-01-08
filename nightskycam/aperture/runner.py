"""
Module defining ApertureRunner
"""

from datetime import datetime
from datetime import time as datetime_time
from enum import Enum
from typing import Optional, cast

from nightskycam_focus.adapter import (
    MAX_FOCUS,
    MIN_FOCUS,
    Aperture,
    adapter,
    set_aperture,
    set_focus,
)
from nightskycam_serialization.status import ApertureRunnerEntries, CamRunnerEntries
from nightskyrunner.config_getter import ConfigGetter
from nightskyrunner.runner import ThreadRunner, status_error
from nightskyrunner.status import Level, NoSuchStatusError, Status
from nightskyrunner.wait_interrupts import RunnerWaitInterruptors


class Opening(Enum):
    OPENED = 0
    CLOSED = 1
    UNSET = 2


def _to_time(config_time: str) -> Optional[datetime_time]:
    # Cast config_time to datetime.time.
    # config_time is expected in format "HOUR:MINUTE".

    if config_time == "None":
        return None
    return datetime.strptime(config_time, "%H:%M").time()


def _period_closed(
    start: Optional[datetime_time],
    end: Optional[datetime_time],
    time_now: datetime_time,
) -> bool:
    """
    start being a time from which camera activity should start
    and stop a time at which it should stop, returns True
    if the current time is in the activity interval.
    Returns also True if either start or end is None.
    """

    if start is None:
        return True
    if end is None:
        return True
    if end < start:
        # end record: next day
        if time_now > start or time_now < end:
            return True
    else:
        # end record: same day
        if time_now > start and time_now < end:
            return True
    return False


@status_error
class ApertureRunner(ThreadRunner):
    """
    Runner for closing the aperture during the day, and opening it at night.
    Requires the adapter developed by the robotics ZWE of MPI-IS
    """

    def __init__(
        self,
        name: str,
        config_getter: ConfigGetter,
        frequency: float = 1.0,
        interrupts: RunnerWaitInterruptors = [],
        core_frequency: float = 1.0 / 0.005,
    ) -> None:
        super().__init__(name, config_getter, interrupts, core_frequency)
        self._opening = Opening.UNSET
        self._focus: Optional[int] = None

    def _camera_active(self) -> Optional[bool]:
        try:
            camera_status = Status.retrieve("asi_cam_runner")
            self._status.remove_issue()
        except NoSuchStatusError:
            self._status.set_issue(
                "configuration key 'use_zwo_camera' is True, "
                "but failed to retrieve the status of a runner named  'asi_cam_runner'"
            )
            return None
        d = cast(CamRunnerEntries, camera_status.get()["entries"])
        if d is not None:
            self._status.remove_issue()
            return "yes" in d["active"]
        else:
            self._status.set_issue(
                "configuration key 'use_zwo_camera' is True, "
                "but failed to retrieve the entries from the 'asi_cam_runner' status"
            )
            return None

    def _close_aperture(self, focus: int, reason: str) -> None:
        if self._opening in (Opening.OPENED, Opening.UNSET):
            self.log(Level.info, f"closing aperture: {reason}")
            try:
                with adapter():
                    set_focus(focus)
                    set_aperture(Aperture.MIN)
            except Exception as e:
                raise RuntimeError(f"failed to close aperture: {e}")
            else:
                self._opening = Opening.CLOSED

    def _open_aperture(self, focus: int, reason: str) -> None:
        if (
            self._focus is None
            or self._focus != focus
            or self._opening in (Opening.CLOSED, Opening.UNSET)
        ):
            self.log(Level.info, f"opening aperture (focus: {focus}): {reason}")
            try:
                with adapter():
                    set_focus(focus)
                    set_aperture(Aperture.MAX)
            except Exception as e:
                raise RuntimeError(f"failed to set focus and open aperture: {e}")
            else:
                self._opening = Opening.OPENED
                self._focus = focus

    def _return(
        self,
        status_entries: ApertureRunnerEntries,
        focus: int,
        opened: bool,
        reason: str,
    ) -> None:
        if opened:
            self._open_aperture(focus, reason)
        else:
            self._close_aperture(focus, reason)
        status_entries["status"] = "opened" if opened else "closed"
        status_entries["reason"] = reason
        self._status.entries(status_entries)

    def iterate(self) -> None:

        config = self.get_config()

        status_entries = ApertureRunnerEntries()
        try:
            use = config["use"]
        except KeyError:
            raise RuntimeError(
                "ApertureRunner: the configuration key 'use' (bool) is missing"
            )
        if not type(use) == bool:
            raise TypeError(
                "configuration for 'use' should be a bool, "
                f"got {use} ({type(use)}) instead"
            )
        status_entries["use"] = use
        try:
            use_zwo_camera = config["use_zwo_camera"]
        except KeyError:
            use_zwo_camera = False
        if not type(use_zwo_camera) == bool:
            raise TypeError(
                "configuration for use_zwo_camera should be a bool, "
                f"got {use_zwo_camera} ({type(use_zwo_camera)}) instead"
            )
        status_entries["use_zwo_camera"] = use_zwo_camera
        start = _to_time(str(config["start_time"]))
        stop = _to_time(str(config["stop_time"]))
        status_entries["time_window"] = f"{start} - {stop}"
        try:
            focus = config["focus"]
        except KeyError:
            raise RuntimeError(
                f"ApertureRunner: the configuration key 'focus' (int between {MIN_FOCUS} and {MAX_FOCUS}) is missing"
            )
        if not type(focus) == int:
            raise TypeError(
                "configuration for focus should be an int, "
                f"got {focus} ({type(focus)}) instead"
            )
        if focus < MIN_FOCUS or focus > MAX_FOCUS:
            raise ValueError(
                f"configuration for focus should be between {MIN_FOCUS} and {MAX_FOCUS}"
                f"got {focus}"
            )
        status_entries["focus"] = focus

        # aperture not used, keep open
        if not use:
            return self._return(status_entries, focus, True, "aperture not used")

        # opening / closing based on the status of the camera
        if use_zwo_camera:
            active: Optional[bool] = self._camera_active()
            if active is not None:
                if active:
                    return self._return(status_entries, focus, True, "camera active")
                else:
                    return self._return(status_entries, focus, False, "camera inactive")

        # if not using use_zwo_camera, then must be using start/end time
        time_now = datetime.now().time()
        period_closed = _period_closed(start, stop, time_now)
        if period_closed:
            return self._return(status_entries, focus, False, "day")
        else:
            return self._return(status_entries, focus, True, "night")
