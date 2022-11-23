import typing
import logging
import datetime
from pathlib import Path
from ..types import Configuration
from ..configuration_getter import ConfigurationGetter
from ..skythread import SkyThread
from ..status import Status, SkyThreadStatus
from ..running_threads import RunningThreads
from ..utils import folder_stats
from ..version import __version__

_logger = logging.getLogger("status")


class StatusThreadConfiguration:

    __slots__ = ("update_every", "tmp_dir", "final_dir")

    def __init__(self):
        self.update_every: float = -1.0
        self.tmp_dir: Path = Path("/tmp")
        self.final_dir: Path = Path("/tmp")

    @classmethod
    def from_dict(cls, config: Configuration) -> object:

        instance = cls()

        for field in cls.__slots__:
            if field not in config.keys():
                raise KeyError(
                    f"Configuration for the status thread misses " f"the key: '{field}'"
                )
            else:
                setattr(instance, field, config[field])

        try:
            instance.update_every = float(instance.update_every)
        except Exception as e:
            raise Exception(
                f"failed to cast the configuration value 'update_every' "
                f"({instance.update_every}) to an float: {e}"
            )

        paths = ("tmp_dir", "final_dir")
        for path in paths:
            value_ = getattr(instance, path)
            value = Path(value_)
            try:
                value.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                raise Exception(f"failed to find or create the directory {value}: {e}")
            else:
                setattr(instance, path, value)

        return instance


def _generate_report(
    status: typing.Dict[str, SkyThreadStatus]
) -> typing.Tuple[str, Status]:
    def _report(name: str, s: SkyThreadStatus):
        report = []
        report.append(f"[{s.status.name}] {name}")
        misc = s.misc
        if s.status == Status.running:
            if s._started_running is not None:
                running_for = str(datetime.datetime.now() - s._started_running)
                misc["running for"] = running_for[: running_for.index(".")]
        if s.status == Status.failure:
            if s._error is not None:
                misc["error"] = str(s._error)
        if s.status in (Status.off, Status.failure):
            if s._last_time_running is not None:
                last_time_run = str(datetime.datetime.now() - s._last_time_running)
                misc["last time run"] = last_time_run[: last_time_run.index(".")]
        if s._started_running is not None:
            running_for = str(datetime.datetime.now() - s._started_running)
            misc["running for"] = running_for[: running_for.index(".")]
        for k, v in misc.items():
            report.append(f"{k}: {str(v)}")
        return "\n".join(report)

    report = "\n\n".join([_report(n, s) for n, s in status.items()])
    worse_status = sorted(
        [s.status for s in status.values()], key=lambda status_: status_.value
    )[-1]

    misc_infos: typing.List[str] = []
    misc_infos.append(
        f"local date and time: {datetime.datetime.now().strftime('%m/%d/%Y, %H:%M:%S')}"
    )
    misc_infos.append(f"nightskycam software version {__version__}")

    misc_infos.append(folder_stats.disk_stats())
    misc_infos_str = "\n".join(misc_infos)

    return (
        f"\n{misc_infos_str}\n\n{report}",
        worse_status,
    )


class StatusReportCallback:
    def callback(self, status: Status, report: str) -> None:
        raise NotImplementedError()


class StatusThread(SkyThread):

    callbacks: typing.List[StatusReportCallback] = []

    def __init__(self, config_getter: ConfigurationGetter):
        super().__init__(config_getter, "status")

    @classmethod
    def check_config(cls, config_getter: ConfigurationGetter) -> typing.Optional[str]:
        """
        Returns None if the configuration is valid, a
        string describing why the configuration is invalid
        otherwise. See the documentation of StatusThreadConfiguration.from_dict.
        """
        config = config_getter.get("StatusThread")
        try:
            StatusThreadConfiguration.from_dict(config)
        except Exception as e:
            return str(e)

        return None

    def deploy_test(self) -> None:
        config = typing.cast(
            StatusThreadConfiguration,
            StatusThreadConfiguration.from_dict(
                self._config_getter.get("StatusThread")
            ),
        )
        try:
            config.tmp_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            raise e.__class__(f"failed to create the folder {config.tmp_dir}: {e}")
        try:
            config.final_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            raise e.__class__(f"failed to create the folder {config.final_dir}: {e}")

    def _execute(self):

        # reading the current configuration
        _logger.debug("reading configuration")
        config = typing.cast(
            StatusThreadConfiguration,
            StatusThreadConfiguration.from_dict(
                self._config_getter.get("StatusThread")
            ),
        )

        self._status.set_misc(
            "status report expected every (seconds)", str(config.update_every)
        )

        # getting the status of all running threads
        _logger.info("reading thread status")
        status: typing.Dict[str, SkyThreadStatus] = RunningThreads.get_status()

        # writing content of status into files
        # for thread_name, instance in status.items():
        #    _logger.debug(f"creating status file for {thread_name}")
        #    # writing into files, in tmp folders
        #    status_str = str(instance)
        #    tmp = config.tmp_dir / f"{thread_name}.status"
        #    with open(tmp, "w+") as f:
        #        f.write(status_str)
        #    # copying to final folder (where may be uploaded
        #    # to server by an ftp thread, if any running)
        #    final = config.final_dir / f"{thread_name}.status"
        #    shutil.copy(tmp, final)

        # if nfty activated, also publishing a report
        report, status = _generate_report(status)
        for callback in self.callbacks:
            callback.callback(status, report)

        # sleeping
        _logger.debug(f"sleeping for {config.update_every} seconds")
        self.sleep(config.update_every)
