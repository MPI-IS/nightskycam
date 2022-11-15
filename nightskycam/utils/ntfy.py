import logging
import typing
import requests
import json
import ntfy_lite
from ..configuration_getter import ConfigurationGetter
from ..types import Configuration


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
