import threading
import logging
import typing
import time
from .configuration_getter import ConfigurationGetter
from .status import SkyThreadStatus


_logger = logging.getLogger("skythread")


class SkyThread:
    def __init__(
        self,
        config_getter: ConfigurationGetter,
        name: str = "SkyThread",
        tags: typing.Optional[typing.List[str]] = None,
    ) -> None:
        self._config_getter = config_getter
        self._name = name
        self._thread: typing.Optional[threading.Thread] = None
        self._running = False
        self._status = SkyThreadStatus(name, config_getter, tags=tags)

    def get_status(self):
        return self._status

    def sleep(
        self,
        duration: float,
        precision: float = 0.02,
        interrupt_on_config_change: bool = False,
    ) -> bool:
        st_mtime: typing.Optional[float] = self._config_getter.get_st_mtime()
        start = time.time()
        while time.time() - start < duration:
            if not self._running:
                break
            if (
                interrupt_on_config_change
                and self._config_getter.get_st_mtime() != st_mtime
            ):
                return True
            time.sleep(precision)
        return False

    @classmethod
    def check_config(cls, config_getter: ConfigurationGetter) -> typing.Optional[str]:
        raise NotImplementedError()

    def deploy_test(self) -> typing.Optional[str]:
        raise NotImplementedError()

    def start(self):
        self._thread = threading.Thread(target=self._run)
        self._running = True
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread is not None:
            self._thread.join()
        self._thread = None

    def on_exit(self) -> None:
        # suclasses may override
        pass

    def revive(self):
        if self._thread is None or not self._thread.is_alive():
            _logger.info(f"thread {self._name} not running, trying to restart")
            if self._thread is not None:
                del self._thread
            try:
                self.start()
            except Exception as e:
                self._thread = None
                _logger.error(f"failed to revive thread {self._name}: {e}")

    def _execute(self):
        raise NotImplementedError()

    def _run(self):
        self._running = True
        _logger.info(f"{self.__class__.__name__}: starting")
        while self._running:
            try:
                self._status.set_running()
                self._execute()
            except Exception as e:
                _logger.error(f"{self.__class__.__name__}: {e}")
                self._status.set_failure(str(e))
                return
        _logger.info(f"{self.__class__.__name__}: turning off")
        self.on_exit()
        self._status.set_off()
