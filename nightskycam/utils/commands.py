"""
Module defining the classes Command and CommandDB, which
allows to receive via websockets commands (e.g. bash commands) to execute.

It is used by the [nightskycam.runner.CommandRunner]() runner.
"""

import base64
import subprocess
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Dict, Generator, List, Optional, Union

import tomli
import tomli_w
from nightskycam_serialization.command import (
    CommandResult,
    deserialize_command,
    serialize_command_result,
)
from nightskycam_serialization.status import CommandRunnerEntries
from nightskyrunner.status import Level, Status

from .websocket_manager import WebsocketReceiverMixin, WebsocketSenderMixin

_running_command: Optional["Command"] = None


class Command:
    """
    Class that can be used to run a terminal command in the backgroud.
    Usage:

    ```python
    command = Command()
    command.command("ls /tmp")
    command.start()
    while not command.executed():
      time.sleep(0.1)
    print(command.stdout)
    print(command.stderr)
    print(command.error)
    print(command.exit_code)
    ```

    """

    __slots__ = (
        "command_id",
        "command",
        "stdout",
        "stderr",
        "exit_code",
        "error",
        "_thread",
        "_lock",
        "_started",
    )

    def __init__(self) -> None:
        self.command_id: int = -1
        self.command: str = ""
        self.stdout: bytes = b""
        self.stderr: bytes = b""
        self.error: str = ""
        self.exit_code: str = ""
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._started: bool = False

    @classmethod
    def from_dict(cls, command: Dict[str, Any]) -> "Command":
        """
        Construct an instance of Command from a dictionary,
        by mapping the values of the dictionary keys "command_id",
        "command", "stdout", "stderr", "error" and "exit_code" to
        the respective instance's attributes.
        """
        instance = cls()
        for attr in [a for a in cls.__slots__ if not a.startswith("_")]:
            setattr(instance, attr, command[attr])
        return instance

    @staticmethod
    def _std_to_str(value: Union[bytes, str]) -> str:
        # cast value, the std output or std error of a command,
        # to a string. Uses base64 for tiff images.
        if isinstance(value, str):
            return value
        try:
            value_out = value.decode("utf-8")
        except UnicodeDecodeError:
            # We will end here for binary data, e.g. the output
            # of commands such as
            #   `cat /tmp/image.tiff`
            value_out = "[tiff]" + base64.b64encode(value).decode("utf-8")
        return value_out

    def get_result(self) -> CommandResult:
        """
        Returns the corresponding instance of CommandResult.
        The stdout and stderr, which are the "output" of the bash
        command, are bytes. They are cast either to utf-8, or if that
        fails, to base64 with prefix "[tiff]" (because it is then assumed
        the command was a 'snapshot' command issued by a nightskycam server
        and that stdout was the corresponding content of a 'tiff' image file).
        """

        return CommandResult(
            self.command_id,
            self.command,
            self._std_to_str(self.stdout),
            self._std_to_str(self.stderr),
            self.exit_code,
            self.error,
        )

    def to_dict(self) -> Dict[str, Any]:
        """
        Returns a dictionary representation of
        this Command instance (keys: "command_id",
        "command", "stdout", "stderr", "error" and "exit_code")
        """
        results = {
            attr: getattr(self, attr)
            for attr in self.__slots__
            if not attr.startswith("_") and attr not in ("stdout", "stderr")
        }
        results["stdout"] = self._std_to_str(self.stdout)
        results["stderr"] = self._std_to_str(self.stderr)
        return results

    def _run(self) -> None:
        try:
            output = subprocess.run(
                self.command, capture_output=True, shell=True
            )
        except Exception as e:
            self.error = str(e)
            self.exit_code = "1"
        with self._lock:
            self.exit_code = str(output.returncode)
            if self.exit_code == "":
                self.exit_code = "0"
            self.stdout = output.stdout
            self.stderr = output.stderr

    def start(self) -> None:
        """
        Request to start running the command in the background.
        It is assumed the attribute Command has been defined.
        """
        self._thread = threading.Thread(target=self._run)
        self._thread.start()
        self._started = True

    def started(self) -> bool:
        """
        Returns True if start has been called.
        """
        return self._started

    def executed(self) -> bool:
        """
        Returns True if start has been called
        and the command finished executing.
        """
        with self._lock:
            r = self.exit_code != ""
            return r


@contextmanager
def read_commands(
    command_path: Path,
) -> Generator[Dict[int, Command], None, None]:
    """
    Context manager for storing in a (toml) file
    a list of [Command](commands). This list of
    instances of [Command](commands) is yielded, and
    their attributes can be updated. On exit, the
    updated instances are saved back to the file.
    The file is created if it does not exist yet.

    Yields
      A dictionary with:
      - keys: an integer representing the (unique) command id of the command,
      - values: the corresponding instance of [Command](command).
    """

    # key: command_id as int.
    # value: dict representation of an instance of Command
    if not command_path.parent.is_dir():
        command_path.parent.mkdir(parents=True)
    if not command_path.is_file():
        with open(command_path, "wb+") as f:
            tomli_w.dump({}, f)
    with open(command_path, "rb") as f:
        all_commands = tomli.load(f)
    commands = {
        int(key): Command.from_dict(value)
        for key, value in all_commands.items()
    }
    yield commands
    updated_commands = {
        str(command.command_id): command.to_dict()
        for command in commands.values()
        if not command._started
    }
    with open(command_path, "wb") as f:
        tomli_w.dump(updated_commands, f)


class CommandDB(WebsocketReceiverMixin, WebsocketSenderMixin):
    """
    An instance of CommandDB will manage a websocket connection,
    for both receiving commands to execute and to sending back the
    corresponding "output" (stdout, stderr and exit code).

    Information regarding
    commands to run are stored in a toml file (see [read_commands]()).

    Usage (see [CommandDB.iterate](iterate) for more details):

    ```python
    command_db = CommandDB()
    while True:
      command_db.iterate(
        Path("/tmp/commands.toml"),
        "wss://myserver:443",
      )
      try:
        time.sleep(1.0)
      except KeyboardInterrupt:
        break
    command_db.on_exit()
    ```

    Or, to ensure the "on_exit" method (which closes the websocket connection)
    is called:

    ```
    with get_commandDB() as command_db:
      ...  # same code as above
    ```
    """

    def __init__(self) -> None:
        WebsocketReceiverMixin.__init__(self)
        WebsocketSenderMixin.__init__(self)
        self._executed_commands: List[int] = []

    def on_exit(self):
        """
        close the websocket connections
        """
        self.sender_stop()
        self.receiver_stop()

    def _get_commands(
        self,
        url: str,
        token: Optional[str],
        cert_file: Optional[Path],
    ) -> List[Command]:
        r: List[Command] = []
        # getting commands from websockets
        # (i.e. commands requested by users via
        # the django webserver)

        messages = self.get(url, cert_file=cert_file)
        for message in messages:
            # message: tuple(command id: int, command: str)
            command_id, command_str = deserialize_command(message, token=token)
            command = Command()
            command.command_id = int(command_id)
            command.command = command_str
            r.append(command)
        return r

    def _inform_server(
        self,
        finished_command: Command,
        status: Optional[Status],
        url: str,
        token: Optional[str],
        cert_file: Optional[Path],
    ) -> None:
        # sending to server output of executed commands
        # (for informing users of the django server)

        result = finished_command.get_result()
        message = serialize_command_result(result, token=token)
        self.send(url, message, status=status, cert_file=cert_file)

    def iterate(
        self,
        command_file: Path,
        url: str,
        token: Optional[str] = None,
        cert_file: Optional[Path] = None,
        status: Optional[Status] = None,
        log_fn: Optional[Callable[[Level, str], None]] = None,
    ) -> CommandRunnerEntries:
        """
        This function does:
        1. read the "command_file" toml file which maintains the list of commands to execute.
        2. add new commands to the list of commands. New commands may have been received via websocket since
         the last call to iterate.
        3. if no command is currently running, starts a new command (if any to execute)
        4. if a command finished execution, send the resulting output to the server via websocket
        5. save back the updated list of commands to the toml file

        where:
        - command_id can be cast to an int. It will serve as (unique) id for this
          new command (if another command with the same id has been previously
          received, and has not been executed yet, it will be overwritten by this new
          command).
        - command is a string representing the command to execute.

        Arguments:
          command_file: path to the toml file keeping tracks of the commands to
            execute (see [read_commands]())
          url: for connecting to the server via websocket
          token: django token, if the server requests one
          cert_file: the public certificate of the server, if it requests one
          status: values related to the command being run will be added to it
          log_fn: information on commands being run will be logged

        Returns:
          A status summary of the commands.
        """

        global _running_command
        status_dict = CommandRunnerEntries()

        # reading the command file, i.e. toml serialized
        # instances of Command (write commands back at exit of context)
        with read_commands(command_file) as commands:
            # informing the world of the number of commands waiting
            # to be executed
            if status:
                command_ids: List[int] = list(commands.keys())
                status_dict["queued_commands"] = command_ids

            # reading new commands from websockets
            new_commands: List[Command] = self._get_commands(
                url, token, cert_file
            )
            for command in new_commands:
                if command.command_id not in commands.keys():
                    commands[command.command_id] = command

            # if no command is already running, starting one
            if _running_command is None and commands:
                _running_command = commands[min(commands.keys())]
                if log_fn:
                    log_fn(
                        Level.info,
                        f"starting command {_running_command.command_id}",
                    )
                if not _running_command.executed():
                    _running_command.start()
                    _running_command._started = True
                    if status:
                        status_dict["active_command"] = str(
                            _running_command.command_id
                        )
                        status.activity(
                            f"running command {_running_command.command_id}"
                        )

            # the running command (if any) finished.
            # sending report to the server
            else:
                if _running_command and _running_command.executed():
                    self._executed_commands.append(_running_command.command_id)
                    if log_fn:
                        log_fn(
                            Level.info,
                            f"finished command {_running_command.command_id} "
                            + f"with exit-code {_running_command.exit_code}",
                        )
                    self._inform_server(
                        _running_command, status, url, token, cert_file
                    )
                    try:
                        del commands[_running_command.command_id]
                    except KeyError:
                        pass
                    _running_command = None

            # informing the world that ...
            if _running_command is None and status:
                status_dict["active_command"] = "-"
            if self._executed_commands and status:
                # ... there is an active command
                status_dict["executed_commands"] = list(
                    self._executed_commands
                )
            return status_dict


@contextmanager
def get_commandDB() -> Generator[CommandDB, None, None]:
    """
    Context manager for [CommandDB]() which ensures any
    open websocket connection is closed upon exit.
    """
    commandDB = CommandDB()
    yield commandDB
    commandDB.on_exit()
