"""
Module for testing [nightskycam.status.runner.StatusRunner]().
"""

import time
from queue import Queue
from typing import Any, Dict, Generator

import pytest
from nightskycam.status.runner import StatusRunner
from nightskycam.tests.runner import TestRunner
from nightskycam.utils.test_utils import (ConfigTester, configuration_test,
                                          get_manager, runner_started,
                                          wait_for, websocket_connection_test)
from nightskycam.utils.websocket_manager import websocket_server
from nightskycam_serialization.serialize import IncorrectToken
from nightskycam_serialization.status import deserialize_status
from nightskyrunner.config import Config
from nightskyrunner.shared_memory import SharedMemory
from nightskyrunner.status import State, wait_for_status


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


class _StatusRunnerConfig:
    url = "127.0.0.1"
    port = 8765
    uri = f"ws://{url}:{port}"

    @classmethod
    def get_config(cls, unsupported: bool = False) -> Config:
        if unsupported:
            return {
                "url": "ws://not_a_server",
            }
        else:
            return {
                "frequency": 5.0,
                "url": cls.uri,
                "system": "test_nightskycam",
                "token": "test_token",
            }

    @classmethod
    def get_config_tester(cls) -> ConfigTester:
        return ConfigTester(
            cls.get_config(unsupported=False),
            cls.get_config(unsupported=True),
        )


def test_connection_status_runner(reset_memory) -> None:
    """
    Testing instances of StatusRunner can connect/disconnect
    to a websocket server.
    """
    config: Config = _StatusRunnerConfig.get_config()

    websocket_connection_test(StatusRunner, _StatusRunnerConfig.port, config)


def test_configuration_status_runner(reset_memory) -> None:
    """
    Testing instances of StatusRunner behave correctly
    to changes of configuration.
    """
    config_tester = _StatusRunnerConfig.get_config_tester()
    with websocket_server(_StatusRunnerConfig.port):
        configuration_test(StatusRunner, config_tester, timeout=30.0)


def _get_message(q: Queue) -> str:
    try:
        message = q.get(timeout=5.0)
    except q.Empty:  # type: ignore
        raise RuntimeError(
            "The websocket server did not receive any status " "(waited 5 seconds)"
        )
    return message


def _get_iteration(all_status: Dict[str, Dict[str, Any]]) -> int:
    test_runner_status = all_status[TestRunner.__name__]
    return int(test_runner_status["entries"]["iteration"])


def test_status_runner(reset_memory) -> None:
    """
    Testing basic functionality of StatusRunner, i.e.
    sending status of other runners to the websocket server
    """

    config: Config = _StatusRunnerConfig.get_config()

    # starting nightskyrunner manager, spawning StatusRunner
    # and TestRunner
    with get_manager((StatusRunner, config), (TestRunner, TestRunner.default_config())):
        # waiting for the instance of StatusRunner to be running
        # before starting the websocket server
        wait_for(runner_started, True, args=(StatusRunner.__name__,))
        # starting websocket server
        with websocket_server(_StatusRunnerConfig.port) as ws_server:
            # the status runner collects the status from other runners
            # (in this case the test runner) and send them to the websocket.
            queue_receive, queue_send, nb_clients = ws_server
            # waiting for the status runner to connect to the websocket server
            wait_for(nb_clients, 1)
            # waiting for the status and the test runners to be running
            for runner_class in (StatusRunner, TestRunner):
                wait_for_status(runner_class.__name__, State.running, timeout=2.0)
            # the message is expected to be the status report sent by the
            # status runner
            message = _get_message(queue_receive)
            manager_name, all_status = deserialize_status(message)
            # 3: manager + status and test runner
            assert len(all_status) == 3
            assert set(all_status.keys()) == set(
                ("test_manager", StatusRunner.__name__, TestRunner.__name__)
            )
            # test runner writes its number of iteration in its status
            start_iteration = _get_iteration(all_status)
            ts = time.time()
            # checking the test runner status, as sent by the status runner,
            # is being kept up to date
            while True:
                message = _get_message(queue_receive)
                manager_name, all_status = deserialize_status(message)
                iteration = _get_iteration(all_status)
                if iteration > start_iteration:
                    break
                if time.time() - ts > 5.0:
                    raise RuntimeError(
                        "test runner status iteration should be increasing, "
                        "no increase observed in 5 seconds"
                    )


@pytest.mark.parametrize("incorrect_token", ["incorrect_token", None])
def test_status_runner_incorrect_token(incorrect_token, reset_memory) -> None:
    """
    Testing an IncorrectToken error is raised when
    the remote sends status with an incorrect token
    Testing basic functionality of StatusRunner, i.e.
    sending status of other runners to the websocket server
    """

    correct_token = "correct_token"

    # the runner is configured with an incorrect token
    config: Config = _StatusRunnerConfig.get_config()
    config["token"] = incorrect_token

    # starting nightskyrunner manager, spawning StatusRunner
    # and TestRunner
    with get_manager((StatusRunner, config), (TestRunner, TestRunner.default_config())):
        # waiting for the instance of StatusRunner to be running
        # before starting the websocket server
        wait_for(runner_started, True, args=(StatusRunner.__name__,))
        # starting websocket server
        with websocket_server(_StatusRunnerConfig.port) as ws_server:
            # the status runner collects the status from other runners
            # (in this case the test runner) and send them to the websocket.
            queue_receive, queue_send, nb_clients = ws_server
            # waiting for the status runner to connect to the websocket server
            wait_for(nb_clients, 1)
            # waiting for the status and the test runners to be running
            for runner_class in (StatusRunner, TestRunner):
                wait_for_status(runner_class.__name__, State.running, timeout=2.0)
            # the message is expected to be the status report sent by the
            # status runner
            message = _get_message(queue_receive)
            # the message has been sent with an incorrect token, checking
            # an error is raised.
            with pytest.raises(IncorrectToken):
                manager_name, all_status = deserialize_status(
                    message, token=correct_token
                )
