import logging
import typing
from logging.handlers import RotatingFileHandler
from .types import Configuration


def _set_log(config: Configuration) -> None:

    handlers: typing.List[typing.Union[logging.StreamHandler, RotatingFileHandler]] = [
        logging.StreamHandler()
    ]
    if config["local_log_file"]:
        handlers.append(
            RotatingFileHandler(
                config["local_log_file"], maxBytes=1048576, backupCount=3
            )
        )
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(name)s - %(levelname)s - %(message)s",
        handlers=handlers,
    )
