import time
import typing
import logging
from ..types import Configuration
from ..utils.http import HttpServer
from ..skythread import SkyThread
from ..configuration_getter import ConfigurationGetter
from ..configuration_file import configuration_file_folder

logger = logging.getLogger("http")


class HttpThread(SkyThread):
    def __init__(self, config_getter: ConfigurationGetter):
        super().__init__(config_getter, "http")
        self._started = False
        self._server: typing.Optional[HttpServer] = None

    @classmethod
    def check_config(cls, config_getter: ConfigurationGetter) -> typing.Optional[str]:
        config: Configuration = config_getter.get("HttpThread")
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
        config = self._config_getter.get("HttpThread")
        with HttpServer(configuration_file_folder(), int(config["port"])):
            time.sleep(0.5)

    def on_exit(self) -> None:
        if self._server is not None:
            self._server.stop()

    def _execute(self) -> None:

        if not self._started:

            config = self._config_getter.get("HttpThread")
            port = int(config["port"])
            self._server = HttpServer(configuration_file_folder(), port)
            self._server.start()
            self._started = True
            self._status.set_misc("serving at port", str(config["port"]))
