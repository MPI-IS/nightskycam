import logging
import typing
from ..skythread import SkyThread
from ..configuration_getter import ConfigurationGetter
from ..types import Configuration
from ..utils.command_file import (
    execute_new_command,
    get_remote_command_file,
    CommandResult
)
from ..utils import ntfy

_logger = logging.getLogger("command")


class CommandThread(SkyThread):
    def __init__(
        self, config_getter: ConfigurationGetter, ntfy: typing.Optional[bool] = True
    ):
        super().__init__(config_getter, "http", ntfy=ntfy)

    @classmethod
    def check_config(cls, config_getter: ConfigurationGetter) -> typing.Optional[str]:
        config: Configuration = config_getter.get("CommandThread")
        try:
            url = config["url"]
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
                f"failed to search remote configuration file" f"from {config['url']}: {e}"
            )

    def _feedback(self, output: CommandResult) -> None:
        def _tags(output: CommandResult) -> typing.List[str]:
            if output.return_code == 0:
                return ["hammer_and_wrench"]
            return ["tornado"]

        def _ntfy_level(output: CommandResult) -> int:
            if output.return_code == 0:
                return 3
            return 4

        if output is None:
            _logger.debug("no new command file")
            return
        if output.return_code == 0:
            _logger.info(f"executed {output.filename} with return code 0")
        else:
            _logger.error(
                f"executed {output.filename} with " "return code {output.return_code}"
            )
        ntfy.safe_publish(
            self._config_getter,
            _ntfy_level(output),
            f"executed command: {output.filename} (return code: {output.return_code})",
            f"stdout:\n{output.stdout}\nstderr:\n{output.stderr}",
            _tags(output),
        )

    def _execute(self) -> None:

        _logger.debug("reading configuration")
        config = self._config_getter.get("CommandThread")

        try:
            output = execute_new_command(config["url"])
        except Exception as e:
            _logger.error("failed to execute command: {e}")
        else:
            self._feedback(output)

        self.sleep(float(config["update_every"]))
