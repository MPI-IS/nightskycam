"""
Unit tests for the [nightskycam.utils.commands](commands) module.
"""

import random
import tempfile
import time
from pathlib import Path
from typing import Generator

import pytest
import tomli
from nightskycam_serialization.command import (CommandResult,
                                               deserialize_command_result,
                                               serialize_command)
from nightskycam_serialization.serialize import IncorrectToken

from nightskycam.utils.commands import Command, CommandDB, get_commandDB
from nightskycam.utils.websocket_manager import websocket_server


@pytest.fixture
def tmp_dir(request, scope="function") -> Generator[Path, None, None]:
    folder_ = tempfile.TemporaryDirectory()
    folder = Path(folder_.name)
    yield folder
    folder_.cleanup()


@pytest.fixture
def commandDB(request, scope="function") -> Generator[CommandDB, None, None]:
    with get_commandDB() as command_db:
        yield command_db


def test_command_from_dict_to_dict():
    """
    Testing an instance of Command can
    be created via a dictionary.
    """
    command_dict = {
        "command_id": 1,
        "command": "ls",
        "stdout": "",
        "stderr": "",
        "error": "",
        "exit_code": None,
    }
    command = Command.from_dict(command_dict)
    command_dict_back = command.to_dict()
    assert command_dict_back == command_dict


def test_command_start_and_executed():
    """
    Testing an instance of Command can
    indeed execute a command.
    """
    command = Command()
    command.command = "echo 'Hello, World!'"
    assert not command.started()
    assert not command.executed()
    command.start()
    command._thread.join()  # wait for the thread to finish
    assert command.started()
    assert command.executed()
    command_result = command.get_result()
    assert command_result.stdout.strip() == "Hello, World!"


@pytest.mark.parametrize("correct_command", [True, False])
def test_execute_one_command(correct_command, tmp_dir, commandDB) -> None:
    """
    Testing CommandDB can receive commands, execute them
    and send proper reports back.
    """
    url = "127.0.0.1"
    port = 8765
    uri = f"ws://{url}:{port}"
    if correct_command:
        command = "echo 'hello world'"
    else:
        command = "not a known command"
    expected_stdout = "hello world"
    command_id = 5
    command_file = tmp_dir / "commands.toml"
    token = "testpass"

    with websocket_server(port) as webserver:
        queue_receive, queue_send, _ = webserver
        # for initializing the websocket connections
        commandDB.iterate(command_file, uri, token=token)
        # this will result in the websocket server to send
        # this command, which should be received by commandDB
        queue_send.put(serialize_command(command_id, command, token=token))
        # iterate will receive the command, execute it, and
        # send a report to the server. The server will put
        # this report in queue_received
        time_start = time.time()
        while time.time() - time_start < 2.0:
            commandDB.iterate(command_file, uri, token=token)
            if not queue_receive.empty():
                break
        if queue_receive.empty():
            raise RuntimeError("the server did not receive any command feedback")

    result_message = queue_receive.get()
    result: CommandResult = deserialize_command_result(result_message, token=token)

    assert result.command_id == command_id
    assert result.command == command

    if correct_command:
        assert result.stdout.strip() == expected_stdout
        assert result.stderr.strip() == ""
        assert int(result.exit_code) == 0
    else:
        assert result.stderr.strip()
        assert int(result.exit_code) != 0


def test_incorrect_token(tmp_dir, commandDB) -> None:
    """
    Testing CommandDB raises an error upon incorrect
    token
    """
    url = "127.0.0.1"
    port = 8765
    uri = f"ws://{url}:{port}"
    command = "echo 'hello world'"
    command_id = 5
    command_file = tmp_dir / "commands.toml"
    token = "testpass"
    incorrect_token = "not_testpass"

    with websocket_server(port) as webserver:
        queue_receive, queue_send, _ = webserver
        # for initializing the websocket connections
        commandDB.iterate(command_file, uri, token=token)
        # this will result in the websocket server to send
        # this command, which should be received by commandDB
        queue_send.put(serialize_command(command_id, command, token=incorrect_token))
        # iterate will receive the command, but should detect the token is
        # incorrect and raise a related error
        with pytest.raises(IncorrectToken):
            time_start = time.time()
            while time.time() - time_start < 2.0:
                commandDB.iterate(command_file, uri, token=token)
                if not queue_receive.empty():
                    break


def test_execute_several_commands(tmp_dir, commandDB) -> None:
    """
    Testing CommandDB can manage several asynchronous commands
    """
    url = "127.0.0.1"
    port = 8765
    uri = f"ws://{url}:{port}"
    nb_commands = 5
    commands = [f"echo '{index}'" for index in range(nb_commands)]
    command_file = tmp_dir / "commands.toml"
    token = "testpass"

    with websocket_server(port) as webserver:
        queue_receive, queue_send, _ = webserver
        commandDB.iterate(command_file, uri, token=token)
        for command_id, command in enumerate(commands):
            queue_send.put(serialize_command(command_id, command, token=token))
            commandDB.iterate(command_file, uri, token=token)
            time.sleep(random.random() * 0.5)
        time_start = time.time()
        while queue_receive.qsize() != nb_commands:
            commandDB.iterate(command_file, uri, token=token)
            time.sleep(0.05)
            if time.time() - time_start > 5.0:
                raise RuntimeError(
                    f"the server did not receive the {nb_commands} expected command feedbacks"
                )

    reports = []
    while not queue_receive.empty():
        r = tomli.loads(queue_receive.get())
        reports.append(r)
    stdouts = set([int(report["stdout"].strip()) for report in reports])
    assert stdouts == set([_ for _ in range(nb_commands)])
