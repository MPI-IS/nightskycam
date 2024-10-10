"""
Module for testing [nightskycam.config_update.runner.ConfigUpdateRunner]()
"""

import tempfile
from pathlib import Path
from typing import Generator

import pytest
import tomli_w
from nightskycam_serialization.config import serialize_config_update
from nightskyrunner.config import Config
from nightskyrunner.shared_memory import SharedMemory
from nightskyrunner.status import State, Status, wait_for_status

from nightskycam.config_update.runner import ConfigUpdateRunner
from nightskycam.tests.runner import TestRunner
from nightskycam.utils.test_utils import (
    ConfigTester,
    configuration_test,
    get_manager,
    runner_started,
    wait_for,
    websocket_connection_test,
)
from nightskycam.utils.websocket_manager import websocket_server

URL = "127.0.0.1"
PORT = 8765


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


def test_connection_status_runner(tmp_dir, reset_memory) -> None:
    """
    Testing instances of ConfigUpdateRunner can connect/disconnect
    to a websocket server.
    """

    config: Config = {
        "frequency": 5.0,
        "url": f"ws://{URL}:{PORT}",
    }

    websocket_connection_test(ConfigUpdateRunner, PORT, config)


class _ConfigUpdateRunnerConfig:
    @classmethod
    def get_config(cls, unsupported: bool = False) -> Config:
        if unsupported:
            return {
                "url": "ws://not_a_server",
            }
        else:
            return {
                "frequency": 5.0,
                "url": f"ws://{URL}:{PORT}",
                "token": "testtoken",
            }

    @classmethod
    def get_config_tester(cls) -> ConfigTester:
        return ConfigTester(
            cls.get_config(unsupported=False),
            cls.get_config(unsupported=True),
        )


def test_configuration(reset_memory) -> None:
    """
    Testing instances of StatusRunner behave correctly
    to changes of configuration.
    """
    config_tester = _ConfigUpdateRunnerConfig.get_config_tester()
    with websocket_server(PORT):
        configuration_test(ConfigUpdateRunner, config_tester, timeout=30.0)


def _get_status_value() -> int:
    # the TestRunner write in the status the
    # value associate with the key "value"
    # in the config.
    # This function retrieve this value from
    # the status of the runner.

    status = Status.retrieve(TestRunner.__name__)
    try:
        entries = status.get()["entries"]
    except ValueError:
        r = -1
    if entries is None:
        r = -1
    else:
        r = entries["value"]  # type: ignore
    return r


def test_config_update_runner(tmp_dir) -> None:
    """
    Testing ConfigUpdateRunner can change configuration of other
    runners successfully.
    """

    def _write_test_runner_config(config: Config, toml_path: Path) -> None:
        with open(toml_path, "wb") as f:
            tomli_w.dump(config, f)

    test_runner_config_file = tmp_dir / "test_runner_config.toml"
    test_runner_config = TestRunner.default_config()
    _write_test_runner_config(test_runner_config, test_runner_config_file)

    config: Config = {
        "frequency": 5.0,
        "url": f"ws://{URL}:{PORT}",
        "token": "testtoken",
    }

    with get_manager(
        (ConfigUpdateRunner, config), (TestRunner, test_runner_config_file)
    ):
        wait_for(runner_started, True, args=(ConfigUpdateRunner.__name__,))
        with websocket_server(PORT) as ws_server:
            queue_receive, queue_send, nb_clients = ws_server
            wait_for(nb_clients, 1)
            for runner_class in (ConfigUpdateRunner, TestRunner):
                wait_for_status(
                    runner_class.__name__, State.running, timeout=2.0
                )

            # having the websocket server sending a new config.
            # TestRunner will write config["value"] in its status.
            # The function _get_iteration above will get the status
            # and return the value written by the runner.
            set_value = 20
            test_runner_config = TestRunner.default_config()
            test_runner_config["value"] = set_value
            config_update_message = serialize_config_update(
                TestRunner.__name__,
                test_runner_config,
                token=str(config["token"]),
            )
            # sending the message
            queue_send.put(config_update_message)
            # waiting for the runner to write new value in its status,
            # meaning its configuration has been successfully updated.
            wait_for(_get_status_value, set_value)


@pytest.mark.parametrize("incorrect_token", ["nothtetoken", None])
def test_config_update_runner_incorrect_token(
    incorrect_token, tmp_dir
) -> None:
    """
    Testing ConfigUpdateRunner switches to error mode when receiveing
    messages with incorrect token.
    """

    def _write_test_runner_config(config: Config, toml_path: Path) -> None:
        with open(toml_path, "wb") as f:
            tomli_w.dump(config, f)

    test_runner_config_file = tmp_dir / "test_runner_config.toml"
    test_runner_config = TestRunner.default_config()
    _write_test_runner_config(test_runner_config, test_runner_config_file)

    config: Config = {
        "frequency": 5.0,
        "url": f"ws://{URL}:{PORT}",
        "token": "testtoken",
    }

    with get_manager(
        (ConfigUpdateRunner, config), (TestRunner, test_runner_config_file)
    ):
        wait_for(runner_started, True, args=(ConfigUpdateRunner.__name__,))
        with websocket_server(PORT) as ws_server:
            queue_receive, queue_send, nb_clients = ws_server
            wait_for(nb_clients, 1)
            for runner_class in (ConfigUpdateRunner, TestRunner):
                wait_for_status(
                    runner_class.__name__, State.running, timeout=2.0
                )

            # having the websocket server sending a new config.
            # TestRunner will write config["value"] in its status.
            # The function _get_iteration above will get the status
            # and return the value written by the runner.
            set_value = 20
            test_runner_config = TestRunner.default_config()
            test_runner_config["value"] = set_value
            config_update_message = serialize_config_update(
                TestRunner.__name__, test_runner_config, token=incorrect_token
            )
            # sending the message
            queue_send.put(config_update_message)
            # waiting for the runner to switch to error mode
            # due to incorrect token
            wait_for_status(
                ConfigUpdateRunner.__name__, State.error, timeout=2.0
            )
