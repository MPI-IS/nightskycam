import typing
import time
import threading
import copy
from ..configuration_getter import ConfigurationGetter
from ..skythread import SkyThread


class DummyThread(SkyThread):
    def __init__(self, config_getter: ConfigurationGetter):
        super().__init__(config_getter, "dummy")
        self._nb_exec = 0
        self._error: typing.Optional[str] = None
        self._lock = threading.Lock()

    @classmethod
    def check_config(cls, config_getter: ConfigurationGetter) -> typing.Optional[str]:
        return None

    def set_error(self, error: str) -> None:
        with self._lock:
            self._error = error

    def del_error(self) -> None:
        with self._lock:
            self._error = None

    def deploy_test(self) -> None:
        return None

    def _execute(self):

        self._nb_exec += 1

        self._status.set_misc("nb_exec", str(self._nb_exec))

        with self._lock:
            error = copy.deepcopy(self._error)

        if error is not None:
            raise Exception(error)

        time.sleep(0.01)
