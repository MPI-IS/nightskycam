from enum import Enum
import ntfy_lite
import logging
import toml
import datetime
import typing
import copy
from threading import Lock
from .utils import ntfy
from .configuration_getter import ConfigurationGetter

_logger = logging.getLogger("ntfy")


class Status(Enum):
    running = (0,)
    starting = (1,)
    off = (2,)
    failure = (3,)


StatusMarker = {
    Status.running: "*",
    Status.off: "o",
    Status.failure: "!",
    Status.starting: "-",
}

StatusPriority = {
    Status.running: 3,
    Status.starting: 3,
    Status.off: 3,
    Status.failure: 4,
}

StatusTags = {
    Status.running: "green_square",
    Status.failure: "red_square",
    Status.off: "black_large_square",
    Status.starting: "blue_square",
}


class NtfyStatus:

    status_tags = {
        Status.running: "green_square",
        Status.failure: "red_square",
        Status.off: "black_large_square",
        Status.starting: "blue_square",
    }

    status_priorities = {
        Status.running: ntfy_lite.Priority.DEFAULT,
        Status.failure: ntfy_lite.Priority.HIGH,
        Status.off: ntfy_lite.Priority.DEFAULT,
        Status.starting: ntfy_lite.Priority.DEFAULT,
    }

    def __init__(self):
        self.title: str = "untitled"
        self.tags: typing.List[str] = []
        self.priority = ntfy_lite.Priority.DEFAULT
        self.message: str = "no message"
        self.time = datetime.datetime.now().strftime("%m/%d/%Y, %H:%M:%S")

    @classmethod
    def get(
        cls,
        name: str,
        current_status: Status,
        previous_status: typing.Optional[Status],
        tags: typing.List[str],
        misc: typing.Dict[str, str],
        error: typing.Optional[str],
        last_time_running: typing.Optional[datetime.datetime],
        started_running: typing.Optional[datetime.datetime],
    ) -> object:

        instance = cls()

        messages: typing.List[str] = []

        if previous_status is None:
            instance.title = f"{name}: {current_status.name}"
        else:
            instance.title = f"{name}: {previous_status.name}->{current_status.name}"
            messages.append(f"- status change at {instance.time}")

        instance.tags.append(cls.status_tags[current_status])
        instance.tags += tags

        instance.priority = cls.status_priorities[current_status]

        if current_status == Status.running:
            if started_running is not None:
                running_for = datetime.datetime.now() - started_running
                messages.append(f"- running for: {running_for}")

        elif current_status in (Status.failure, Status.off):
            if last_time_running is not None:
                did_not_run_for = datetime.datetime.now() - last_time_running
                messages.append(f"- did not run for: {did_not_run_for}")

        elif current_status == Status.starting:
            instance.title = f"{name}: starting status"
            instance.priority = 3

        if error:
            messages.append(f"- error: {error}")

        if misc:
            for key, value in misc.items():
                messages.append(f"- {key}: {value}")

        instance.message = "\n".join(messages)

        if not instance.message:
            instance.message = "-"

        return instance


class SkyThreadStatus:
    def __init__(
        self,
        name: str,
        config_getter: ConfigurationGetter,
        tags: typing.Optional[typing.List[str]] = None,
        ntfy: typing.Optional[bool] = True,
    ) -> None:
        self._name = name
        self._status = Status.starting
        self._last_time_running: typing.Optional[datetime.datetime] = None
        self._started_running: typing.Optional[datetime.datetime] = None
        self._error: typing.Optional[str] = None
        self._misc: typing.Dict[str, str] = {}
        if not tags:
            self._tags: typing.List[str] = []
        else:
            self._tags = tags
        self._config_getter = config_getter
        self._lock = Lock()
        self._ntfy = ntfy
        if self._ntfy:
            self._ntfy_publish(None)

    def _ntfy_publish(self, previous_status: typing.Optional[Status]) -> None:

        if not self._ntfy:
            return

        if previous_status is not None:
            _logger.info(
                f"{self._name}: change status from {previous_status.name} to {self._status.name}"
            )
        else:
            _logger.info(f"{self._name}: new status {self._status.name}")

        try:
            pconfig = ntfy.publish_config(self._config_getter)
        except Exception as e:
            _logger.error(
                f"skipping to publish the status (or the status change) of {self._name}, "
                f"because failed to read the configuration file: {e}"
            )
            return
        if pconfig is None:
            return
        else:
            url, topic = pconfig

        ntfy_status = typing.cast(
            NtfyStatus,
            NtfyStatus.get(
                self._name,
                self._status,
                previous_status,
                self._tags,
                self._misc,
                self._error,
                self._last_time_running,
                self._started_running,
            ),
        )

        try:
            ntfy.publish(
                url,
                topic,
                ntfy_status.priority,
                ntfy_status.title,
                ntfy_status.message,
                ntfy_status.tags,
            )
        except Exception as e:
            _logger.error(str(e))

    @property
    def name(self) -> str:
        with self._lock:
            return self._name

    @property
    def error(self) -> typing.Optional[str]:
        with self._lock:
            return self._error

    @property
    def tags(self) -> typing.List[str]:
        with self._lock:
            return copy.deepcopy(self._tags)

    @property
    def misc(self) -> typing.Dict[str, str]:
        with self._lock:
            return copy.deepcopy(self._misc)

    @property
    def status(self) -> Status:
        with self._lock:
            return self._status

    @property
    def running_for(self) -> typing.Optional[str]:
        with self._lock:
            if not self._started_running:
                return None
            running_for = datetime.datetime.now() - self._started_running
            return str(running_for)

    @property
    def did_not_run_for(self) -> typing.Optional[str]:
        with self._lock:
            if not self._last_time_running:
                return None
            duration = datetime.datetime.now() - self._last_time_running
            return str(duration)

    def add_tag(self, tag: str) -> None:
        with self._lock:
            self._tags.append(tag)

    def remote_tag(self, tag) -> None:
        with self._lock:
            try:
                index = self._tags.index(tag)
            except ValueError:
                return
            del self._tags[index]

    def set_misc(self, key: str, value: str) -> None:
        with self._lock:
            self._misc[key] = value

    def del_misc(self, key) -> None:
        with self._lock:
            if key in self._misc:
                del self._misc[key]

    def _ntfy_on_status_change(set_status_fn):
        def ntfy(self, error: typing.Optional[str] = None):
            previous_status = self._status
            if error is None:
                set_status_fn(self)
            else:
                set_status_fn(self, error)
            if self._status != previous_status:
                self._ntfy_publish(previous_status)

        return ntfy

    @_ntfy_on_status_change
    def set_running(self) -> None:
        with self._lock:
            self._error = None
            self._status = Status.running
            if self._started_running is None:
                self._started_running = datetime.datetime.now()

    @_ntfy_on_status_change
    def set_off(self) -> None:
        with self._lock:
            if self._status == Status.running:
                self._last_time_running = datetime.datetime.now()
            self._status = Status.off
            self._started_running = None

    @_ntfy_on_status_change
    def set_failure(self, error: str) -> None:
        with self._lock:
            if self._status == Status.running:
                self._last_time_running = datetime.datetime.now()
            self._error = error
            self._status = Status.failure
            self._started_running = None

    def __str__(self) -> str:
        with self._lock:
            d = {}
            d["status"] = self._status.name
            if self._status == Status.running:
                if self._started_running is not None:
                    running_for = datetime.datetime.now() - self._started_running
                d["running_for"] = str(running_for)
            if self._status == Status.failure:
                if self._error is not None:
                    d["error"] = str(self._error)
            if self._status in (Status.off, Status.failure):
                if self._last_time_running is not None:
                    last_time_run = str(
                        datetime.datetime.now() - self._last_time_running
                    )
                    d["last_time_run"] = last_time_run
        return toml.dumps(d)
