import logging
import typing
from ..skythread import SkyThread
from ..configuration_getter import ConfigurationGetter
from ..types import Configuration
from ..command_file import (
    download_new_command,
    get_remote_command_file,
    CommandResult,
    CommandRun,
)
from ..local_command_file import execute_local_command

_logger = logging.getLogger("command")


class CommandCallback:
    def callback(self, output: typing.Optional[CommandResult]) -> None:
        raise NotImplementedError()


class _LoggerCallback(CommandCallback):
    def callback(self, output: typing.Optional[CommandResult]) -> None:
        if output is None:
            _logger.debug("no new command file")
            return
        if output.return_code == 0:
            _logger.info(f"executed {output.filename} with return code 0")
        else:
            _logger.error(
                f"executed {output.filename} with " f"return code {output.return_code}"
            )


class CommandThread(SkyThread):

    callbacks: typing.List[CommandCallback] = [_LoggerCallback()]

    def __init__(self, config_getter: ConfigurationGetter):
        super().__init__(config_getter, "command", tags=["hammer_and_wrench"])
        self._command_run: typing.Optional[CommandRun] = None
        self._last_result: typing.Optional[CommandResult] = None

    @classmethod
    def check_config(cls, config_getter: ConfigurationGetter) -> typing.Optional[str]:
        config: Configuration = config_getter.get("CommandThread")
        try:
            config["url"]
        except KeyError:
            return "failed to find the required key 'url'"
        try:
            update_every = config["update_every"]
        except KeyError:
            return "failed to find required key 'update_every'"
        try:
            float(update_every)
        except Exception:
            return str(
                f"failed to cast the value of they key 'update_every' "
                f"({update_every}) to an float"
            )
        return None

    def deploy_test(self) -> None:
        config = self._config_getter.get("CommandThread")
        try:
            get_remote_command_file(config["url"])
        except Exception as e:
            raise Exception(
                f"failed to search remote configuration file"
                f"from {config['url']}: {e}"
            )

    def _previous_result(self) -> str:
        if self._last_result is None:
            return "no previous command"
        return f"output of last command:\nstdout:\n{self._last_result.stdout}\nstderr:\n{self._last_result.stderr}"

    def _execute(self) -> None:

        _logger.debug("reading configuration")
        config = self._config_getter.get("CommandThread")

        if self._command_run is not None:
            status: typing.Optional[str] = self._command_run.status()
            if status is None:
                self._status.set_misc("current command", "no command running")
                result = self._command_run.result()
                for callback in self.callbacks:
                    callback.callback(result)
                self._last_result = result
                self._command_run = None
            else:
                self._status.set_misc("current command", status)
        else:
            self._status.set_misc("current command", "no command running")

        if self._command_run is None:
            timeout = 10.0
            filepath = download_new_command(config["url"], timeout)
            if filepath is not None:
                self._command_run = CommandRun(filepath)
                self._status.set_misc(
                    "current command", str(self._command_run.status())
                )

        if self._command_run is None:
            try:
                output = execute_local_command()
            except Exception as e:
                _logger.error(f"failed to execute local command: {e}")
            else:
                if output:
                    for callback in self.callbacks:
                        callback.callback(output)

        self._status.set_misc("previous command output", self._previous_result())

        self.sleep(float(config["update_every"]))
