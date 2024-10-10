import argparse
import logging
import os
import sys
import time
from pathlib import Path

from nightskyrunner.config_toml import DynamicTomlManagerConfigGetter
from nightskyrunner.log import set_logging
from nightskyrunner.manager import Manager
from nightskyrunner.status import Level


_logger = logging.Logger("executable")


def _set_log(level=Level.info) -> None:
    stdout = True
    set_logging(stdout, level=level)


def _get_default_config_path() -> Path:
    filepath = Path(os.getcwd()) / "nightskycam.toml"
    return filepath


def _how_to() -> str:
    return str(
        "run nightskycam-start, optionally passing the path to a toml configuration file "
        "as argument. If no argument is passed, the software will assume a 'nightskycam.toml' "
        "configuration file in the current directory"
    )


def _get_config_path() -> Path:
    if len(sys.argv) > 1:
        path = Path(sys.argv[1])
    else:
        path = _get_default_config_path()
    if not path.is_file():
        _logger.info(_how_to())
        _logger.error(f"failed to find the configuration file {path}")
        raise FileNotFoundError(str(path))
    return path


def _run(config_path: Path) -> None:
    _logger.info(
        f"starting nightskycam using the configuration file {config_path}"
    )
    manager_config_getter = DynamicTomlManagerConfigGetter(config_path)
    with Manager(manager_config_getter, name="nightskycam"):
        while True:
            try:
                time.sleep(0.2)
            except KeyboardInterrupt:
                _logger.info("keyboard interrupt")
                break
    _logger.info("exiting nightskycam")


def execute() -> None:
    try:
        _set_log()
        config_path = _get_config_path()
        _run(config_path)
    except Exception as e:
        _logger.error(f"error while running nightskycam: {e}")
        sys.exit(1)
    sys.exit(0)


def repetitive_starting_test() -> None:
    """
    Runs a [nightskycam.utils.test_utils.repetitive_runner_starting_test](),
    i.e. managers will be spawned, run for a while and stop, for as many
    iterations as configured. The test will exit earlier if any
    runner switches to an error state, in which case it will log the
    name of the faulty runner and the related error message.

    This test may be useful to detect error which occurs sometimes, but not
    always, after start.

    (The concrete case motivating the development of this test are StatusRunner
    sometimes failing to establish a websocket connection due to some SSL issue.)
    """
    _set_log(level=Level.debug)

    manager_toml = Path(__file__).parent.resolve() / "manager.toml"
    parser = argparse.ArgumentParser(
        description=str(
            "Run a repetitive starting test, i.e. will start and stop "
            "a nightskycam manager several times, but exit as soon as "
            "one of the runner switches to an error state. A file "
            "manager.toml is expected in the current directory."
        )
    )

    parser.add_argument(
        "-max-iterations",
        type=int,
        default=10,
        help="Optional: number of iterations, i.e. number of managers that will be started and stopped (int).",
    )

    # Add the 'run-for' argument
    parser.add_argument(
        "-run-for",
        type=float,
        default=10.0,
        help="Optional: Duration of each run in seconds (float).",
    )

    # Parse the arguments
    args = parser.parse_args()

    from nightskycam.utils.test_utils import repetitive_runner_starting_test

    repetitive_runner_starting_test(
        manager_toml, run_for=args.run_for, max_iterations=args.max_iterations
    )


if __name__ == "__main__":
    execute()
