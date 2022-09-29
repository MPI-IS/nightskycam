import signal
import os
import time
import sys
import typing
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from .configuration_file import configuration_file_folder
from .configuration_getter import DynamicConfigurationGetter
from . import manager
from .utils.ftp import FtpConfig, FtpServer
from .utils.http import HttpServer
from .utils.ntfy import NtfyHandler

_logger = logging.getLogger("main")


class _ColoredFormatter(logging.Formatter):

    grey = "\x1b[38;20m"
    yellow = "\x1b[33;20m"
    red = "\x1b[31;20m"
    bold_red = "\x1b[31;1m"
    reset = "\x1b[0m"
    format_ = "[%(levelname)s] %(asctime)s | %(name)s |  %(message)s"

    FORMATS = {
        logging.DEBUG: grey + format_ + reset,
        logging.INFO: grey + format_ + reset,
        logging.WARNING: yellow + format_ + reset,
        logging.ERROR: red + format_ + reset,
        logging.CRITICAL: bold_red + format_ + reset,
    }

    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt)
        return formatter.format(record)


def _set_log(
    local_log_file: typing.Optional[Path], config_getter: DynamicConfigurationGetter
) -> None:

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(_ColoredFormatter())

    ntfy_handler = NtfyHandler(config_getter)
    ntfy_handler.setLevel(logging.ERROR)

    handlers: typing.List[
        typing.Union[logging.StreamHandler, RotatingFileHandler, NtfyHandler]
    ] = [stream_handler, ntfy_handler]
    if local_log_file is not None:
        handlers.append(
            RotatingFileHandler(local_log_file, maxBytes=1048576, backupCount=3)
        )
    logging.basicConfig(
        level=logging.INFO,
        format="[%(levelname)s] %(asctime)s | %(name)s |  %(message)s",
        datefmt="%d-%b-%y %H:%M:%S",
        handlers=handlers,
    )


def http_test_server():

    folder = Path(os.getcwd())
    with HttpServer(folder) as server:
        print()
        print(f"-started server at port: {server.get_port()}")
        print()
        try:
            while True:
                time.sleep(0.2)
        except KeyboardInterrupt:
            pass
        except Exception as e:
            print(f"exit with error: {e}")


def ftp_test_server():

    config = FtpConfig(
        username="test",
        passwd="12345",
        folder=Path(os.getcwd()),
    )

    server = FtpServer(config)

    print("starting serving current folder at ftp://127.0.0.1:2121")
    server.start()

    try:
        while True:
            time.sleep(0.2)
    except KeyboardInterrupt:
        server.stop()
    except Exception as e:
        print(f"exit with error: {e}")


def _deploy_tests():

    main_dir = configuration_file_folder()
    if not main_dir.is_dir():
        raise FileNotFoundError(
            f"failed to start nightskycam, main folder {main_dir} not found"
        )

    os.chdir(main_dir)

    config_file = main_dir / "nightskycam_config.toml"
    if not config_file.is_file():
        raise FileNotFoundError(
            f"failed to start nightskycam, main config file {config_file} not found"
        )

    config_getter = DynamicConfigurationGetter(config_file)

    manager.deploy_tests(config_getter)


def deploy_tests():

    try:
        print()
        _deploy_tests()
    except Exception as e:
        print("\n* nightskycam deployment tests *failed* :", file=sys.stderr)
        print(e, file=sys.stderr)
        print("\n", file=sys.stderr)
        exit(1)

    print("\n* nightskycam deployment tests: success\n")
    exit(0)


def _run(main_control: manager.MainControl):

    main_dir = configuration_file_folder()
    if not main_dir.is_dir():
        raise FileNotFoundError(
            f"failed to start nightskycam, main folder {main_dir} not found"
        )

    os.chdir(main_dir)

    config_file = main_dir / "nightskycam_config.toml"
    if not config_file.is_file():
        raise FileNotFoundError(
            f"failed to start nightskycam, main config file {config_file} not found"
        )

    config_getter = DynamicConfigurationGetter(config_file)

    config = config_getter.get("main")
    local_log_file: typing.Optional[Path]
    try:
        local_log_file = Path(config["local_log_file"])
    except KeyError:
        local_log_file = None
    if local_log_file is not None:
        try:
            local_log_file.parent.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            raise Exception(
                f"failed to create the requested log directory "
                f"({local_log_file.parent}): {e}"
            )

    _set_log(local_log_file, config_getter)

    _logger.info("starting nightskycam")
    manager.run(main_control, config_getter)


def run():

    main_control = manager.MainControl()

    def sigterm_handle(signal, frame):
        main_control.running = False

    signal.signal(signal.SIGTERM, sigterm_handle)

    try:
        _run(main_control)
    except Exception as e:
        import traceback

        print()
        print("------")
        traceback.print_exc()
        print("------")
        print()
        _logger.error(f"nightskycam stopping with error: {e}")
        exit(1)

    exit(0)
