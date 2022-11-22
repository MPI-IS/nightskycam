import logging
import datetime
import typing
import ntfy_lite
from ..status import StatusChangeCallback, Status
from ..configuration_getter import ConfigurationGetter
from ..types import Configuration
from ..skythreads import command_thread, config_thread, status_thread
from ..command_file import CommandResult


def publish_config(
    config_getter: ConfigurationGetter,
) -> typing.Optional[typing.Tuple[str, str]]:

    config: Configuration = config_getter.get("main")

    if "ntfy" not in config:
        return None

    ntfy_config = config["ntfy"]
    url = ntfy_config["url"]
    topic = ntfy_config["topic"]

    return url, topic


def publish(
    url: str,
    topic: str,
    priority: ntfy_lite.Priority,
    title: str,
    message: str,
    tags: typing.List[str],
) -> None:

    ntfy_lite.push(topic, title, message=message, tags=tags, priority=priority)


def safe_publish(
    config_getter: ConfigurationGetter,
    priority: ntfy_lite.Priority,
    title: str,
    message: str,
    tags: typing.List[str],
):
    try:
        ntfy_config = publish_config(config_getter)
    except Exception:
        return
    if ntfy_config is None:
        return
    url, topic = ntfy_config
    publish(url, topic, priority, title, message, tags)


class NtfyHandler(logging.Handler):

    _ntfy_priority = {
        logging.CRITICAL: 5,
        logging.ERROR: 4,
        logging.WARNING: 4,
        logging.INFO: 3,
        logging.DEBUG: 2,
        logging.NOTSET: 1,
    }

    _ntfy_tags = {
        logging.CRITICAL: ["fire"],
        logging.ERROR: ["broken_heart"],
        logging.WARNING: ["warning"],
        logging.INFO: ["artificial_satellite"],
        logging.DEBUG: ["speech_balloon"],
        logging.NOTSET: [],
    }

    def __init__(self, config_getter: ConfigurationGetter):
        super().__init__()
        self._config_getter = config_getter
        self._url: typing.Optional[str] = None
        self._topic: typing.Optional[str] = None
        self._last_messages: typing.Dict[str, str] = {}
        self._update_config()

    def _update_config(self) -> None:
        try:
            ntfy_config = publish_config(self._config_getter)
        except Exception:
            return
        if ntfy_config is None:
            return
        self._url, self._topic = ntfy_config

    def _is_new_record(self, record: logging.LogRecord) -> bool:
        try:
            previous_message = self._last_messages[record.name]
        except KeyError:
            self._last_messages[record.name] = record.msg
            return True
        if record.msg == previous_message:
            return False
        self._last_messages[record.name] = record.msg
        return True

    def emit(self, record):
        if not self._is_new_record(record):
            return
        self._update_config()
        if self._url is None:
            return
        if self._topic is None:
            return
        try:
            publish(
                self._url,
                self._topic,
                self._ntfy_priority[record.levelno],
                record.name,
                record.msg,
                self._ntfy_tags[record.levelno],
            )
        except Exception:
            pass


class _NtfyStatus:

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


class NtfyStatusChangeCallback(StatusChangeCallback):
    def __init__(self, config_getter: ConfigurationGetter):
        self._config_getter = config_getter

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

        ntfy_status = typing.cast(
            _NtfyStatus,
            _NtfyStatus.get(
                name,
                status,
                previous_status,
                tags,
                miscs,
                error,
                last_time_running,
                started_running,
            ),
        )

        print()
        print("NTFY !")
        print(ntfy_status.priority)
        print()
        
        safe_publish(
            self._config_getter,
            ntfy_status.priority,
            ntfy_status.title,
            ntfy_status.message,
            ntfy_status.tags,
        )


class NtfyCommandThreadCallback(command_thread.CommandCallback):
    def __init__(self, config_getter: ConfigurationGetter):
        self._config_getter = config_getter

    def callback(self, output: typing.Optional[CommandResult]) -> None:

        if output is None:
            return

        def _tags(output: CommandResult) -> typing.List[str]:
            if output.return_code == 0:
                return ["hammer_and_wrench"]
            return ["tornado"]

        def _ntfy_level(output: CommandResult) -> ntfy_lite.Priority:
            if output.return_code == 0:
                return ntfy_lite.Priority.DEFAULT
            return ntfy_lite.Priority.HIGH

        safe_publish(
            self._config_getter,
            _ntfy_level(output),
            f"executed command: {output.filename} (return code: {output.return_code})",
            f"stdout:\n{output.stdout}\nstderr:\n{output.stderr}",
            _tags(output),
        )


class NtfyConfigThreadCallback(config_thread.ConfigChangeCallback):
    def __init__(self, config_getter: ConfigurationGetter):
        self._config_getter = config_getter

    def callback(self, new_config: str) -> None:
        safe_publish(
            self._config_getter,
            ntfy_lite.Priority.DEFAULT,
            "new configuration file",
            f"now using configuration file {new_config}",
            ["new"],
        )


class NtfyStatusThreadCallback(status_thread.StatusReportCallback):

    StatusPriority = {
        Status.running: ntfy_lite.Priority.DEFAULT,
        Status.starting: ntfy_lite.Priority.DEFAULT,
        Status.off: ntfy_lite.Priority.DEFAULT,
        Status.failure: ntfy_lite.Priority.HIGH,
    }

    StatusTags = {
        Status.running: "green_square",
        Status.failure: "red_square",
        Status.off: "black_large_square",
        Status.starting: "blue_square",
    }

    def __init__(self, config_getter: ConfigurationGetter):
        self._config_getter = config_getter

    def callback(self, status: Status, report: str) -> None:
        safe_publish(
            self._config_getter,
            self.StatusPriority[status],
            "threads status report",
            report,
            [self.StatusTags[status], "technologist"],
        )
