from enum import Enum
import threading
import toml
import datetime
import typing
import copy
from threading import Lock
from .configuration_getter import ConfigurationGetter


class Status(Enum):
    running = (0,)
    starting = (1,)
    off = (2,)
    failure = (3,)


class StatusChangeCallback:
    def callback(
        self,
        name: str,
        status: Status,
        previous_status: typing.Optional[Status] = None,
        tags: typing.List[str] = [],
        miscs: typing.Dict[str, str] = {},
        error: str = "",
        last_time_running: typing.Optional[datetime.datetime] = None,
        started_running: typing.Optional[datetime.datetime] = None,
    ) -> None:
        raise NotImplementedError()


class SkyThreadStatus:

    callbacks: typing.List[StatusChangeCallback] = []
    _callbacks_lock = threading.Lock()

    def __init__(
        self,
        name: str,
        config_getter: ConfigurationGetter,
        tags: typing.Optional[typing.List[str]] = None,
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
        for callback in self.callbacks:
            callback.callback(self._name, self._status)

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

    def _status_change_callbacks(  # type: ignore
        set_status_fn: typing.Callable[[typing.Any, ...], typing.Any]  # type: ignore
    ):
        def _c(self, error: typing.Optional[str] = None):
            previous_status = self._status
            if error is None:
                set_status_fn(self)  # type: ignore
            else:
                set_status_fn(self, error)  # type: ignore
            if self._status != previous_status:
                for callback in self.callbacks:
                    with self._callbacks_lock:
                        callback.callback(
                            self._name,
                            self._status,
                            previous_status=previous_status,
                            tags=self._tags,
                            miscs=self._misc,
                            error=self._error,
                            last_time_running=self._last_time_running,
                            started_running=self._started_running,
                        )

        return _c

    @_status_change_callbacks  # type: ignore
    def set_running(self) -> None:
        with self._lock:
            self._error = None
            self._status = Status.running
            if self._started_running is None:
                self._started_running = datetime.datetime.now()

    @_status_change_callbacks  # type: ignore
    def set_off(self) -> None:
        with self._lock:
            if self._status == Status.running:
                self._last_time_running = datetime.datetime.now()
            self._status = Status.off
            self._started_running = None

    @_status_change_callbacks
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
