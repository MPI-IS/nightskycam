import subprocess
import logging
import typing
import time
from pathlib import Path
from ..skythread import SkyThread
from ..configuration_getter import ConfigurationGetter
from ..configuration_file import configuration_file_folder
from ..types import Configuration

_logger = logging.getLogger("webdav")


def _run_webdav(target_dir: Path, port: int = 8008) -> subprocess.Popen:
    command = f"exec wsgidav --host=0.0.0.0 --port={port} --root={target_dir} --auth=anonymous"
    process = subprocess.Popen(command, shell=True)
    return process


def get_ip() -> typing.List[str]:
    ips = subprocess.check_output(["hostname", "-I"])
    return ips.decode("UTF-8").split()


class WebdavThread(SkyThread):
    def __init__(
        self, config_getter: ConfigurationGetter, ntfy: typing.Optional[bool] = True
    ):
        super().__init__(config_getter, "webdav", ntfy=ntfy)
        self._started = False
        self._process: typing.Optional[subprocess.Popen] = None

    @classmethod
    def check_config(cls, config_getter: ConfigurationGetter) -> typing.Optional[str]:
        config: Configuration = config_getter.get("WebdavThread")
        try:
            port = config["port"]
        except KeyError:
            return "failed to find the required key 'port'"
        try:
            int(port)
        except Exception:
            return f"failed to cast the value of they key 'port' ({port}) to an int"
        return None

    def deploy_test(self) -> None:
        config = self._config_getter.get("WebdavThread")
        process = _run_webdav(configuration_file_folder(), int(config["port"]))
        time.sleep(1)
        process.kill()

    def on_exit(self) -> None:
        if self._process is not None:
            self._process.kill()
            self._process = None

    def _execute(self) -> None:

        if not self._started:
            config = self._config_getter.get("WebdavThread")
            port = int(config["port"])
            ips = ", ".join(get_ip())
            _logger.info(f"starting webdav server at port {port} (IPs: {ips})")
            self._process = _run_webdav(configuration_file_folder(), port)
            self._started = True
            self._status.set_misc("serving at port", str(config["port"]))
            self._status.set_misc("IP(s)", ips)
