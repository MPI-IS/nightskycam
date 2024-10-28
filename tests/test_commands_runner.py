import random
import tempfile
from pathlib import Path
from queue import Queue
from typing import Callable, Generator, Tuple

import pytest
import tomli
from nightskycam.commands.runner import CommandRunner
from nightskycam.utils.test_utils import (ConfigTester, configuration_test,
                                          get_manager, runner_started,
                                          wait_for, websocket_connection_test)
from nightskycam.utils.websocket_manager import websocket_server
from nightskycam_serialization.command import serialize_command
from nightskyrunner.config import Config
from nightskyrunner.shared_memory import SharedMemory
from nightskyrunner.status import State, wait_for_status


@pytest.fixture
def tmp_dir(request, scope="function") -> Generator[Path, None, None]:
    """
    Fixture yielding a temp directory.
    """
    folder_ = tempfile.TemporaryDirectory()
    folder = Path(folder_.name)
    try:
        yield folder
    finally:
        folder_.cleanup()


@pytest.fixture
def reset_memory(
    request,
    scope="function",
) -> Generator[None, None, None]:
    """
    Fixture clearing the nightskyrunner shared memory
    upon exit.
    """
    yield None
    SharedMemory.clear()


class _CommandRunnerConfig:
    command_file = "command_tests.toml"
    token = "testpass"
    url = "127.0.0.1"
    port = 8765
    uri = f"ws://{url}:{port}"

    @classmethod
    def get_config(cls, temp_dir: Path, unsupported: bool = False) -> Config:
        if unsupported:
            return {
                "command_file": "/not/exiting/file",
                "url": "ws://not_a_server",
            }
        else:
            return {
                "frequency": 5.0,
                "command_file": str(temp_dir / cls.command_file),
                "url": cls.uri,
                "token": cls.token,
            }

    @classmethod
    def get_config_tester(cls, temp_dir: Path) -> ConfigTester:
        return ConfigTester(
            cls.get_config(temp_dir, unsupported=False),
            cls.get_config(temp_dir, unsupported=True),
        )


def _command_runner_test(
    config: Config,
    ws_server: Tuple[Queue, Queue, Callable[[], int]],
) -> None:
    # have the server send a command, and checking the
    # server then receives a suitable report from
    # the runner.
    command_id = random.randint(1, 10000)
    command = f"echo '{command_id}'"
    queue_receive, queue_send, nb_clients = ws_server
    # waiting for the instance of CommandRunner to be connected
    # to the websocket server (i.e. nb_clients != 0)
    wait_for(nb_clients, 1)
    wait_for_status(CommandRunner.__name__, State.running, timeout=2.0)
    # sending a command to the runner
    queue_send.put(serialize_command(command_id, command, token=str(config["token"])))
    # waiting for the runner to send the report back
    wait_for(queue_receive.empty, False, runners=CommandRunner.__name__)
    report = tomli.loads(queue_receive.get())
    assert report["stdout"].strip() == str(command_id)


def test_connection_commands_runner(tmp_dir, reset_memory) -> None:
    """
    Testing instances of CommandRunner can connect/disconnect
    to a websocket server.
    """
    config: Config = _CommandRunnerConfig.get_config(tmp_dir)
    websocket_connection_test(CommandRunner, _CommandRunnerConfig.port, config)


def test_commands_runner(tmp_dir, reset_memory) -> None:
    """
    Testing the basic functionalities of an
    instance of CommandRunner (connect to a
    websocket server and executing a basic
    command)
    """

    config: Config = _CommandRunnerConfig.get_config(tmp_dir)

    with get_manager((CommandRunner, config)):
        # waiting for the instance of CommandRunner to be running
        wait_for(runner_started, True, args=(CommandRunner.__name__,))
        with websocket_server(_CommandRunnerConfig.port) as ws_server:
            _command_runner_test(config, ws_server)


@pytest.mark.parametrize("incorrect_token", ["incorrect_token", None])
def test_commands_runner_wrong_token(incorrect_token, tmp_dir, reset_memory) -> None:
    """
    Testing command runner turns to error mode when
    sent commands with wrong token
    """
    command_id = 1
    command = f"echo '{command_id}'"
    config: Config = _CommandRunnerConfig.get_config(tmp_dir)

    with get_manager((CommandRunner, config)):
        # waiting for the instance of CommandRunner to be running
        wait_for(runner_started, True, args=(CommandRunner.__name__,))
        with websocket_server(_CommandRunnerConfig.port) as ws_server:
            queue_receive, queue_send, nb_clients = ws_server
            wait_for_status(CommandRunner.__name__, State.running, timeout=2.0)
            wait_for(nb_clients, 1)
            queue_send.put(
                serialize_command(command_id, command, token=incorrect_token)
            )
            wait_for_status(CommandRunner.__name__, State.error, timeout=2.0)


def test_configuration(tmp_dir, reset_memory) -> None:
    """
    Testing instances of CommandRunner behave correctly
    to changes of configuration.
    """
    config_tester = _CommandRunnerConfig.get_config_tester(tmp_dir)
    with websocket_server(_CommandRunnerConfig.port):
        configuration_test(CommandRunner, config_tester, timeout=30.0)
