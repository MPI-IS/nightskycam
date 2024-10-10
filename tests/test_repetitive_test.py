"""
Unit tests for the [nightskycam.utils.test_utils.runners_starting_test]()
and [nightskycam.utils.test_utils.repetitive_runner_starting_test]() functions.
"""

import os
import random
import tempfile
import time
from pathlib import Path
from threading import Thread
from typing import Dict, Generator, Tuple

import pytest
import tomli
import tomli_w
from nightskyrunner.config import Config
from nightskyrunner.shared_memory import SharedMemory

from nightskycam.tests.runner import TestRunner
from nightskycam.utils.test_utils import (repetitive_runner_starting_test,
                                          runners_starting_test)


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
def write_toml_configs(tmp_dir) -> Generator[Tuple[Path, Dict[str, Path]], None, None]:
    """
    Write toml configuration files for a manager that will start
    two TestRunner runners ('runner1' and 'runner2').
    Yields the path to the manager toml file, and a dictionary with:
    - key: runner name ('runner1' or 'runner2')
    - value: path to related toml configuration file
    """
    runners = ("runner1", "runner2")
    runner_config = TestRunner.default_config()
    runner_config_paths: Dict[str, Path] = {
        runner_name: tmp_dir / f"{runner_name}.toml" for runner_name in runners
    }
    manager_config = {}
    manager_config_path = tmp_dir / "manager.toml"
    for runner_name, runner_path in runner_config_paths.items():
        toml_path = tmp_dir / f"{runner_name}.toml"
        with open(toml_path, "wb") as f:
            tomli_w.dump(runner_config, f)
        manager_config[runner_name] = {
            "class_runner": "nightskycam.tests.runner.TestRunner",
            "class_config_getter": "nightskyrunner.config_toml.DynamicTomlConfigGetter",
            "args": [str(toml_path)],
        }
    with open(manager_config_path, "wb") as f:
        tomli_w.dump(manager_config, f)
    yield (manager_config_path, runner_config_paths)


def _set_config(toml_path: Path, error: bool) -> None:
    with open(toml_path, "rb") as f:
        current = tomli.load(f)
    folder = toml_path.parent
    tmp_file = folder / f"{random.randint(1,10000)}.toml"
    updated_config = {k: v for k, v in current.items()}
    updated_config["error"] = error
    with open(tmp_file, "wb") as f:
        tomli_w.dump(updated_config, f)
    tmp_file.rename(toml_path)


def set_error(toml_path: Path) -> None:
    """
    Update the content of the configuration file to
    set the "error" value to True (an instance of TestRunner will raise an error if its
    'error' key configuration is True, i.e. its state will switch to 'error').
    """
    _set_config(toml_path, True)


def set_ok(toml_path: Path) -> None:
    """
    Update the content of the configuration file to
    set the "error" value to False
    """
    _set_config(toml_path, False)


def test_runners_starting_test_ok(write_toml_configs, reset_memory):
    """
    Checking runners_starting_test returns None when the None (i.e. no error) of the
    runners switch to an error state.
    """
    manager_toml, _ = write_toml_configs
    os.chdir(str(manager_toml.parent))
    output = runners_starting_test(manager_toml, run_for=1.0)
    assert output is None


def test_runners_starting_test_not_ok(write_toml_configs, reset_memory):
    """
    Checking runners_starting_test returns the name of the runner
    that switched to an error state.
    """
    manager_toml, runner_configs = write_toml_configs
    os.chdir(str(manager_toml.parent))

    for error_runner in ("runner2", "runner1"):
        set_error(runner_configs["runner2"])
        output = runners_starting_test(manager_toml, run_for=1.0)
        assert type(output) is tuple
        assert output[0] == "runner2"

        set_ok(runner_configs["runner2"])
        output = runners_starting_test(manager_toml, run_for=1.0)
        assert output is None


def test_repetitive_runner_starting_test_ok(write_toml_configs, reset_memory):
    """
    Checking repetitive_runner_starting_test returns None when the none of the
    runners switch to an error state.
    """
    manager_toml, runner_configs = write_toml_configs
    os.chdir(str(manager_toml.parent))
    output = repetitive_runner_starting_test(
        manager_toml, run_for=1.0, max_iterations=2
    )
    assert output is None


def test_repetitive_runner_starting_test_not_ok(write_toml_configs, reset_memory):
    """
    Checking repetitive_runner_starting_test exits as soon a runner switches
    to an error state.
    """
    manager_toml, runner_configs = write_toml_configs
    os.chdir(str(manager_toml.parent))
    thread = Thread(
        target=repetitive_runner_starting_test, args=(manager_toml, 1.0, 10)
    )
    thread.start()
    time.sleep(2.0)
    set_error(runner_configs["runner2"])
    time_start = time.time()
    thread.join()
    d = time.time() - time_start
    assert d < 1.0
