"""
Module defining ApertureRunner
"""

from nightskyrunner.config_getter import ConfigGetter
from nightskyrunner.runner import ThreadRunner, status_error
from nightskyrunner.status import Level
from nightskyrunner.wait_interrupts import RunnerWaitInterruptors
from nightskycam_serialization.status import (
    CamRunnerEntries,
    ApertureRunnerEntries,
)
from nightskyrunner.status import Status, NoSuchStatusError
from nightskycam_focus.adapter import adapter, Aperture, set_aperture
from enum import Enum
from typing import Optional, cast
from datetime import datetime
from datetime import time as datetime_time


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
        return "yes" in d["active"]

    def _close_aperture(self) -> None:
        if self._opening in (Opening.OPENED, Opening.UNSET):
            try:
                with adapter():
                    set_aperture(Aperture.MIN)
            except Exception as e:
                raise RuntimeError(f"failed to close aperture: {e}")
            else:
                self._opening = Opening.CLOSED

    def _open_aperture(self) -> None:
        if self._opening in (Opening.CLOSED, Opening.UNSET):
            try:
                with adapter():
                    set_aperture(Aperture.MAX)
            except Exception as e:
                raise RuntimeError(f"failed to open aperture: {e}")
            else:
                self._opening = Opening.OPENED

    def _return(
        self, status_entries: ApertureRunnerEntries, opened: bool, reason: str
    ) -> None:
        if opened:
            self.log(Level.info, f"opening aperture: {reason}")
            self._open_aperture()
        else:
            self.log(Level.info, f"closing aperture: {reason}")
            self._close_aperture()
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
        end = _to_time(str(config["end_time"]))
        status_entries["time_window"] = f"{start} - {end}"

        # aperture not used, keep open
        if not use:
            self._return(status_entries, True, "aperture not used")

        # opening / closing based on the status of the camera
        if use_zwo_camera:
            active: Optional[bool] = self._camera_active()
            if active is not None:
                if active:
                    return self._return(status_entries, True, "camera active")
                else:
                    return self._return(
                        status_entries, False, "camera inactive"
                    )

        # if not using use_zwo_camera, then must be using start/end time
        time_now = datetime.now().time()
        period_closed = _period_closed(start, end, time_now)
        if period_closed:
            return self._return(status_entries, False, "day")
        else:
            return self._return(status_entries, True, "night")
