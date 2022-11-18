import logging
import typing
from ..skythread import SkyThread
from ..configuration_getter import ConfigurationGetter
from ..types import Configuration
from ..command_file import execute_new_command, get_remote_command_file, CommandResult
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

    def _execute(self) -> None:

        _logger.debug("reading configuration")
        config = self._config_getter.get("CommandThread")

        try:
            output = execute_new_command(config["url"])
        except Exception as e:
            _logger.error(f"failed to execute command: {e}")
        else:
            for callback in self.callbacks:
                callback.callback(output)

        try:
            output = execute_local_command()
        except Exception as e:
            _logger.error(f"failed to execute local command: {e}")
        else:
            if output:
                for callback in self.callbacks:
                    callback.callback(output)

        self.sleep(float(config["update_every"]))
