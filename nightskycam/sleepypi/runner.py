"""
Module defining SleepyPiRunner.
"""

from datetime import timedelta
import datetime
import subprocess
import time
from datetime import datetime as dtime
from pathlib import Path
from typing import Optional, Tuple

from nightskycam_serialization.status import SleepyPiRunnerEntries
from nightskyrunner.config import Config
from nightskyrunner.config_getter import ConfigGetter
from nightskyrunner.runner import ThreadRunner, status_error
from nightskyrunner.status import Level
from nightskyrunner.wait_interrupts import RunnerWaitInterruptors


def _now() -> datetime.time:
    # easier to mock than
    # dtime.now.
    return dtime.now().time()


def _to_time(config_time: str) -> datetime.time:
    # config_time expected in format "HOUR:MINUTE"

    return dtime.strptime(config_time, "%H:%M").time()


def _ftp_empty(ftp_folder: Optional[Path]) -> bool:
    # True if ftp_folder empty or None

    if ftp_folder is None:
        return True
    return not any(ftp_folder.iterdir())


def _duration_to_event(
    event: datetime.time, time_now: Optional[datetime.time] = None
) -> int:
    # Returns the number of minutes between event and time_now.
    # (if time_now is None, time_now will be set to the current time).
    # If event is before time_now, 0 is returned.

    if time_now is None:
        time_now = _now()

    dt_now = dtime.combine(date=dtime.min.date(), time=time_now)
    dt_event = dtime.combine(date=dtime.min.date(), time=event)

    if time_now < event:
        return int((dt_event - dt_now).total_seconds() / 60)

    if time_now == event:
        return 0

    dt_before_midnight = dtime.combine(
        date=dtime.min.date(), time=datetime.time(23, 59, 0)
    )
    dt_after_midnight = dtime.combine(
        date=dtime.min.date(), time=datetime.time(0, 1, 0)
    )
    return (
        int((dt_before_midnight - dt_now).total_seconds() / 60)
        + int((dt_event - dt_after_midnight).total_seconds() / 60)
        + 2
    )


def _time_to_sleep(
    start_sleep: datetime.time,
    stop_sleep: datetime.time,
    time_now: Optional[datetime.time] = None,
) -> Tuple[int, str]:
    # returns either -1 (the system should sleep now)
    # or a positive number corresponding to the
    # number of minutes until the time the system should
    # go to sleep. Also returns an explanatory string.

    if time_now is None:
        time_now = _now()
    if time_now < start_sleep or time_now > stop_sleep:
        sleep_in = _duration_to_event(start_sleep, time_now=time_now)
        return (
            sleep_in,
            f"wake up time, sleep planned in {sleep_in} minutes",
        )
    r = -1, "sleep time"
    return r


def _sleep_duration(time_now: dtime.time, stop_sleep: dtime.time) -> int:
    # Convert time objects to dtime objects for today
    now = dtime.combine(dtime.today(), time_now)
    stop = dtime.combine(dtime.today(), stop_sleep)

    # If stop_sleep is on the next day, add one day to stop
    if stop < now:
        stop += timedelta(days=1)

    # Calculate the difference in minutes
    duration = int((stop - now).total_seconds() / 60)

    return duration


def _should_sleep(
    ftp_folder: Optional[Path],
    start_sleep: datetime.time,
    stop_sleep: datetime.time,
    time_now: Optional[datetime.time] = None,
) -> Tuple[bool, str, int]:

    # Returns:
    # - should sleep (bool),
    # - reason (string),
    # - number of minutes until sleep (or -1 if should sleep is True)
    #
    # if ftp_folder is not True, will return False if the folder is
    # not empty (i.e. should wait until the ftp folder is empty).

    if time_now is None:
        time_now = _now()

    min_to_sleep, reason = _time_to_sleep(
        start_sleep, stop_sleep, time_now=time_now
    )

    if min_to_sleep < 0:
        if not _ftp_empty(ftp_folder):
            return False, "time to sleep, but ftp folder not empty", -1
        return True, reason, -1

    return False, reason, min_to_sleep


def _start_sleeping(minutes: int, tty: str = "/dev/ttyS0") -> None:

    # /dev/ttyS0: default tty for sleepy pi.
    # Calls the command that will trigger the raspi / sleepy pi to sleep.
    # for the given number of minutes.

    command = f'echo "sleep:{minutes}" > {tty}'
    output = subprocess.run(command, capture_output=True, shell=True)
    exit_code = output.returncode
    stderr = output.stderr.decode("utf-8")
    if exit_code != 0:
        error = str(
            f"sleep command ({command}) failed with exit code {exit_code}: {stderr}"
        )
        raise RuntimeError(error.strip())


@status_error
class SleepyPiRunner(ThreadRunner):
    """
    Runner putting the raspberry pi to sleep when in a given time interval.
    Assumes the raspberry pi has been equiped with a sleepy pi2 and its related
    software, i.e. it is possible to trigger sleeping via a bash command like:

    ```
    # sleeping for the next 30 minutes
    echo "sleep:30" > /dev/ttyS0
    ```

    Configuration keys:

    - sleep: bool, if false the system will never sleep.
    - start_sleep: sleep starting time, in format "Hour:Minutes".
    - stop_sleep: wake up time, in format "Hour:Minutes".
    - ftp_folder: absolute path to a folder.
    - wait_ftp: if true, sleep will not occur until ftp_folder is not empty.
    - tty: the linux TTY the sleepy pi is listening to ("ttyS0" if not specified)

    Note that sleeping is disabled during the first 5 minutes of this runner's activity.
    This is for better support of configuration changes.
    """

    def __init__(
        self,
        name: str,
        config_getter: ConfigGetter,
        interrupts: RunnerWaitInterruptors = [],
        core_frequency: float = 1.0 / 0.005,
    ) -> None:
        super().__init__(name, config_getter, interrupts, core_frequency)
        self._time_started = time.time()
        self._command_sent = False

    def _update_status(
        self,
        config: Config,
        should_sleep: bool,
        sleep_blocked: bool,
        info: str,
        min_to_sleep: int,
    ) -> None:

        # write in the runner status information useful
        # to users.

        values = SleepyPiRunnerEntries()

        sleep = config["sleep"]
        wait_ftp = config["wait_ftp"]

        if not type(sleep) == bool:
            raise TypeError(
                f"configuration for 'sleep' should be a bool, got {sleep} ({type(sleep)}) instead."
            )

        if not type(wait_ftp) == bool:
            raise TypeError(
                f"configuration for 'wait_ftp' should be a bool, got {wait_ftp} ({type(wait_ftp)}) instead."
            )

        if sleep:
            values["configured_to_sleep"] = True
            values["start_sleep"] = str(config["start_sleep"])
            values["stop_sleep"] = str(config["stop_sleep"])
        else:
            values["configured_to_sleep"] = False
        values["wait_for_ftp"] = True if wait_ftp else False
        if should_sleep:
            if sleep_blocked:
                values["status"] = (
                    "should sleep but has to wait at least 5min after reboot"
                )
            else:
                values["status"] = "sending sleep command"
        else:
            values["status"] = f"not sending sleep command ({info})"
        self._status.entries(values)

    def on_exit(self) -> None:
        pass

    def iterate(self) -> None:
        # the sleepy pi can request the system to sleep only after
        # 5 minutes after starting. This is so that if there is any
        # configuration issue with this runner (e.g. it asked the system
        # to always sleep), there is a little time after reboot during
        # which commands / reconfiguration can be received.

        # reading the runner toml config file
        config = self.get_config()
        ftp_folder, start_sleep, stop_sleep = None, None, None
        sleep = bool(config["sleep"])
        wait_ftp = bool(config["wait_ftp"])

        # the runner should not sleep, doing nothing except
        # informing users.
        if not sleep:
            self._update_status(config, False, False, "not set to sleep", -1)
            return

        # the runner is set to sleep during certain intervals
        start_sleep = _to_time(str(config["start_sleep"]))
        stop_sleep = _to_time(str(config["stop_sleep"]))

        # the runner should not sleep if there are files to upload
        if wait_ftp:
            ftp_folder = Path(str(config["ftp_folder"]))
            ftp_folder.mkdir(parents=True, exist_ok=True)

        # checking if the runner should be sleeping now, or later
        should_sleep_, info, min_to_sleep = _should_sleep(
            ftp_folder, start_sleep, stop_sleep
        )

        # the runner should not sleep during the first five minutes of activity.
        # This gives time to the runner to read its configuration again after reboot
        # even if it has been set to sleep all the time (likely by mistake).
        sleep_blocked = False
        if time.time() - self._time_started < 5.0 * 60:
            try:
                override_sleep_blocked = config["override_sleep_blocked"]
            except KeyError:
                override_sleep_blocked = False
                if not override_sleep_blocked:
                    sleep_blocked = True

        # informing users about what is going on.
        self._update_status(
            config, should_sleep_, sleep_blocked, info, min_to_sleep
        )

        # should sleep, but runner just started, so not sleeping yet
        if sleep_blocked and should_sleep_:
            self.log(
                Level.info,
                str(
                    "should sleep now, but has to wait "
                    "at least 5 minutes after boot before getting to sleep."
                ),
            )

        # sleeping now !
        # if self._command_sent is True, a command has already been sent,
        # so not sending the command again (this may be misinterpreted by
        # the sleepy pi)
        if should_sleep_ and (not sleep_blocked) and (not self._command_sent):
            tty: Optional[str]
            try:
                tty = str(config["tty"])
            except KeyError:
                tty = None
            minutes = _sleep_duration(dtime.now().time(), stop_sleep) + 1
            self.log(Level.info, f"sleeping now for {minutes} minutes")
            self._command_sent = True
            if tty is None:
                _start_sleeping(minutes)
            else:
                _start_sleeping(minutes, tty=tty)
