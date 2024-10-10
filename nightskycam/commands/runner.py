"""
Module defining CommandRunner.
"""

from pathlib import Path
from typing import Optional

from nightskycam_serialization.status import CommandRunnerEntries
from nightskyrunner.config_getter import ConfigGetter
from nightskyrunner.runner import ProcessRunner, status_error
from nightskyrunner.wait_interrupts import RunnerWaitInterruptors

from ..utils.commands import CommandDB


@status_error
class CommandRunner(ProcessRunner):
    """
    An instance of Command receives shell command requests from a websocket
    server, executes them, and sends execution reports to the server.

    CommandRunner is a runner wrapper
    over [nightskycam.utils.commands.CommandDB](CommandDB).

    The [nightskyrunner.config_runner.ConfigRunner](config runner) of
    a CommandRunner must have these keys: "command_file", "url",
    "cert_file "and "token".

    For the usage of "command_file", "url" and "password", see
    [nightskycam.utils.commands.CommandDB.iterate]().

    "cert_file" is optional and should be setup to the valid path
    to a public ssl certificate file if the websocket server
    needs it.
    """

    def __init__(
        self,
        name: str,
        config_getter: ConfigGetter,
        interrupts: RunnerWaitInterruptors = [],
        core_frequency: float = 1.0 / 0.005,
    ) -> None:
        super().__init__(name, config_getter, interrupts, core_frequency)
        self._command_db: Optional[CommandDB] = None

    def on_exit(self) -> None:
        # closing websockets
        if self._command_db is not None:
            self._command_db.on_exit()
            self._command_db = None

    def iterate(self) -> None:
        # initializing command db
        if self._command_db is None:
            self._command_db = CommandDB()

        # reading the configuration
        config = self.get_config()
        command_file = Path(str(config["command_file"]))
        url = str(config["url"])
        cert_file: Optional[Path] = None
        try:
            cert_file = Path(str(config["cert_file"]))
        except KeyError:
            pass
        token: Optional[str] = None
        try:
            token = str(config["token"])
        except KeyError:
            pass

        # check path to cert_file is valid,
        # raising exception otherwise
        if cert_file and not cert_file.is_file():
            self.on_exit()
            raise FileNotFoundError(
                f"failed to find the public certificate: {cert_file}"
            )

        if self._command_db:
            # "iterating" command db, i.e.
            # read new commands, monitor the command currently
            # executing (if any), sending reports regarding
            # finished commands (if any)
            status_dict: CommandRunnerEntries = self._command_db.iterate(
                command_file,
                url,
                token=token,
                cert_file=cert_file,
                status=self._status,
                log_fn=self.log,
            )
            self._status.entries(status_dict)
