import typing
import logging
import threading
from .status import SkyThreadStatus
from .skythread import SkyThread
from .types import GlobalConfiguration
from .configuration_getter import ConfigurationGetter
from .configuration_file import get_skythreads

_logger = logging.getLogger("manager")


class RunningThreads:

    skythreads: typing.List[SkyThread] = []
    _lock = threading.Lock()

    @classmethod
    def get_status(cls) -> typing.Dict[str, SkyThreadStatus]:
        with cls._lock:
            all_status = [t.get_status() for t in cls.skythreads]
            return {st._name: st for st in all_status}

    @classmethod
    def get_classes(cls) -> typing.List[typing.Type[SkyThread]]:
        return [sk.__class__ for sk in cls.skythreads]

    @classmethod
    def maintain(cls, config_getter: ConfigurationGetter):
        # read the configuration, and stop/start instances of subclasses
        # of SkyThread according to it
        try:
            configuration: GlobalConfiguration = config_getter.get_global()
        except Exception as e:
            _logger.error(
                f"skipping thread maintenance, because failing to read the configuration file: {e}"
            )
            return
        # skythread classes requested by config
        desired = get_skythreads(configuration)
        # stopping those which are currently running, but should not
        del_indexes = []
        for index, current in enumerate(cls.skythreads):
            if current.__class__ not in desired:
                _logger.info(f"stopping skythread {current.__class__.__name__}")
                current.stop()
                del_indexes.append(index)
        with cls._lock:
            for index in del_indexes:
                del cls.skythreads[index]
        # starting those which are desired but are not running yet
        for d in desired:
            if d not in [current.__class__ for current in cls.skythreads]:
                _logger.info(f"starting skythread {d.__name__}")
                instance = d(config_getter)
                with cls._lock:
                    cls.skythreads.append(instance)
                instance.start()
        # attempting to revive threads which may have passed out
        for thread in cls.skythreads:
            thread.revive()

    @classmethod
    def stop(cls):
        _logger.info("stopping")
        for thread in cls.skythreads:
            _logger.info(
                f"sending stop request to skythread {thread.__class__.__name__}"
            )
            thread.stop()
            _logger.info(f"skythread {thread.__class__.__name__} stopped")
        cls.skythreads = []


class skythreads_stop:
    def __enter__(self):
        return

    def __exit__(self, e_type, e_value, e_traceback):
        if e_type is not None:
            _logger.error(f"exit with exception: {e_value}")
        RunningThreads.stop()
