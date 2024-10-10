"""
Functions useful for unit-testing.
"""

import logging
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path, PosixPath
from typing import (
    Any,
    Callable,
    Generator,
    Iterable,
    Optional,
    Tuple,
    Type,
    TypeVar,
    Union,
    cast,
)

import tomli_w
from nightskyrunner.config import Config
from nightskyrunner.config_toml import (
    DynamicTomlConfigGetter,
    DynamicTomlManagerConfigGetter,
    TomlRunnerFactory,
)
from nightskyrunner.factories import BasicRunnerFactory, RunnerFactory
from nightskyrunner.manager import FixedRunners, Manager
from nightskyrunner.runner import Runner
from nightskyrunner.status import (
    NoSuchStatusError,
    State,
    Status,
    wait_for_status,
)

from nightskycam.utils.websocket_manager import websocket_server


def runners_starting_test(
    manager_toml: Path,
    run_for: float,
    logger: Optional[logging.Logger] = None,
) -> Optional[Tuple[str, str]]:
    """
    Starts a (nightskyrunner) manager based on a toml configuration, and let if run for
    'run_for' seconds.
    If any of the runner switches to an
    [nightskyrunner.status.State](error state), the manager interrupts
    and this function returns a two values tuple:

    - the name of the runner that switched to an error state
    - the related error message

    If none of the runners switches to an error state, None is returned
    after 'run_for' seconds.

    Arguments:
      manager_toml: manager configuration file, see for example
        [nightskyrunner.config_toml.DynamicTomlManagerConfigGetter].
      run_for: maximum time the manager will run (in seconds)
      logger: optional logger

    Returns
      The tuple `(name of the runner, error message)` or None.
    """

    manager_toml = Path("manager.toml")
    manager_config_getter = DynamicTomlManagerConfigGetter(manager_toml)

    time_start = time.time()

    with Manager(manager_config_getter):
        if logger:
            logger.info("starting manager")
        try:
            # running for "run_for" seconds
            while time.time() - time_start < run_for:
                # getting the status of all runners
                all_status = Status.retrieve_all()

                # checking if any of the runner is in error mode
                for status in all_status:
                    error_detected: Union[bool, Tuple[str, str]] = False
                    d = status.get()
                    if d["state"] == State.error.name:
                        error_msg = str(d["error"]["message"])
                        error_detected = (d["name"], error_msg)
                        if logger:
                            logger.info(
                                f"error detected for runner {d['name']}:\n{error_msg}"
                            )
                        # a runner is in error mode, early exit
                        error_detected = cast(Tuple[str, str], error_detected)
                        return error_detected
                time.sleep(0.2)
        except KeyboardInterrupt:
            if logger:
                logger.info("exit (keyboard interrupt)")
            return None
        if logger:
            logger.info("exiting manager")

    return None


def repetitive_runner_starting_test(
    manager_toml: Path,
    run_for: float,
    max_iterations: Optional[int] = None,
) -> Optional[Tuple[str, str]]:
    """
    Runs up to "max_iterations" times the function
    [runners_starting_test](). If any of the test fails
    (i.e. a runner switches to an error test) this function
    exits early and returns the name of the faulty runner and the
    error message. Otherwise the function returns None after
    "max_iterations" iterations.
    """

    logger = logging.getLogger("repetitive-test")
    logger.setLevel(logging.DEBUG)

    iteration = 0

    while True:
        if max_iterations:
            if iteration >= max_iterations:
                break
            iteration += 1
            logger.info(
                f"repetitive starting test iteration {iteration}/{max_iterations}"
            )
        else:
            logger.info("repetitive starting test: new iteration")

        # running a test (spawning a manager, running it for "run_for" seconds,
        # check if any runner switched to error mode)
        error = runners_starting_test(manager_toml, run_for, logger=logger)

        # at least one runner switched to error mode, early exit
        if error:
            logger.info("finished repetitive test with error")
            logger.info(f"error, runner: {error[0]}")
            logger.info(f"error, message: {error[1]}")
            return error
        time.sleep(0.1)

    logger.info("finished repetitive tests, no runner error detected")

    return None


RunnerClassConfig = Union[
    # Runner class, Config (as dict or path to toml file), runner name
    Tuple[Type[Runner], Union[Config, Path], str],
    # similar to above, but infer the runner name by using the name of the runner class
    Tuple[Type[Runner], Union[Config, Path]],
]


@contextmanager
def get_manager(
    *runner_class_configs: RunnerClassConfig,
) -> Generator[Manager, None, None]:
    """
    Starts a Manager running an instance of each of the
    runner_classes. The instance of each runner will
    be its class name.
    If the related config is a dictionary, the runner will use it
    as non mutable configuration. If a path to a toml file,
    then the runner will use it as a dynamic configuration.

    Arguments:
      runner_class_config: the list of 2d tuple:
        - the runner class
        - the corresponding configuration (dict or path)

    Returns:
      corresponding manager
    """

    def _get_runner_factory(
        runner_class_config: RunnerClassConfig,
    ) -> RunnerFactory:
        runner_factory: RunnerFactory
        runner_class = runner_class_config[0]
        config = runner_class_config[1]
        try:
            runner_name = runner_class_config[2]
        # When optional argument (runner name) was not given.
        except IndexError:
            runner_name = runner_class.__name__
        if type(config) is PosixPath:
            runner_factory = TomlRunnerFactory(
                runner_name,
                runner_class,
                DynamicTomlConfigGetter,
                args=[config],
            )
        else:
            config = cast(Config, config)
            runner_factory = BasicRunnerFactory(
                runner_class, config, runner_name=runner_name
            )
        return runner_factory

    # constructing the runner factory, i.e. the factories the manager will use
    # to instantiate the runners
    runner_factories = [
        _get_runner_factory(rcc) for rcc in runner_class_configs
    ]

    # the manager config getter, i.e. the class the manager will use to configure
    # itself, i.e. selecting which runner to instantiate and start.
    # FixedRunners: the manager will start all the runners and will not reevaluate
    # this decision during runtime.
    manager_config_getter = FixedRunners(tuple(runner_factories))

    # constructing the manager
    manager = Manager(manager_config_getter, name="test_manager")

    # running the manager (i.e. spawning all the related runners)
    manager.start()
    try:
        yield manager
    finally:
        manager.stop()


def get_runner_error(runner_name: str) -> Optional[str]:
    """
    Returns the error message associated with this runner,
    if any.
    """
    status = Status.retrieve(runner_name)
    d = status.get()
    try:
        return d["error"]["message"]
    except KeyError:
        return None


def exception_on_error_state(runner_names: Union[str, Iterable[str]]) -> None:
    """
    Check the state associated with each runner name.
    If for any of them the state is 'error', a RuntimeError
    is raised.

    The state is retrieved via:

    ```python
    status = Status.retrieve(runner_name).get_state()
    ```

    If there is no status for one of the runner (i.e. no
    runner of that name has been started), nothing occurs
    (no exception is raised).
    """
    if type(runner_names) == str:
        runner_names = (runner_names,)
    for runner_name in runner_names:
        try:
            status = Status.retrieve(runner_name)
        except NoSuchStatusError:
            pass
        else:
            if status.get_state() == State.error:
                raise RuntimeError(
                    f"Runner {runner_name} is in error state "
                    f"with error {status.get()['error']}"
                )


def runner_started(runner_name: str) -> bool:
    """
    Returns True if a runner of the provided name
    has been started, False otherwise.
    """
    try:
        Status.retrieve(runner_name)
    except NoSuchStatusError:
        return False
    return True


TargetValue = TypeVar("TargetValue")


def wait_for(
    what: Callable[..., TargetValue],
    target_value: TargetValue,
    args: Iterable[Any] = tuple(),
    timeout: float = 2.0,
    time_sleep: float = 0.05,
    runners: Union[str, Iterable[str]] = tuple(),
) -> None:
    """
    Calls 'what' repeatedly until it returns
    a value equal to 'target_value'.
    If this does not occur within 'timeout', a
    RuntimeError is raised.
    If a runner name (or a list of runner names) is provided,
    a RuntimeError will be raised if an error state is detected
    (see [exception_on_error_state]()).

    Arguments:
      what: the function returning the value that will be evaluated.
      target_value: the value that what should return for the function to exit.
      args: arguments for the 'what' function.
      timeout: duration (in seconds) during which 'what' should return a value
        that evalutes to 'sign'.
      time_sleep: interval (in seconds) at which 'what' will be called.
      runners: runner name (or list of runner names) of which related
        [nightskyrunner.runner.Runner](runner) instances should not switch
        to an error state.

    Raises
      RuntimeError if any of the runners switches to an error state.
    """
    time_start = time.time()
    while what(*args) != target_value:
        if time.time() - time_start > timeout:
            raise RuntimeError(
                f"timeout: {what} did not return {target_value} in {timeout} seconds"
            )
        exception_on_error_state(runners)
        time.sleep(time_sleep)


def websocket_connection_test(
    runner_class: Type[Runner], port, config: Config
) -> None:
    """
    It is assumed 'runner_class' is a runner requiring an active websocket connection.
    This function will test that the runner is in a 'running' state when a
    websocket server is up and running, and in a 'error' state otherwise.

    Arguments:
      runner_class: a manager will be instantiated, which will run an instance of
        'runner_class'.
      port: port at which the runner class will attempt to connect to.
      config: the configuration to use for the runner's instance.
    """
    runner_name = runner_class.__name__

    # firt batch of test: the runner is started before the websocket server

    with get_manager((runner_class, config)):
        # waiting for the runner to have been started by the manager
        wait_for(runner_started, True, args=(runner_name,))

        # we did not start a websocket server yet !
        # the runner should catch this and switch to an error state
        if not wait_for_status(runner_name, State.error, timeout=2.0):
            raise RuntimeError(
                f"{runner_class.__name__} did not switch to error state when starting "
                "at a time no websocket server is running."
            )

        # starting the websocket server
        with websocket_server(port):
            # the runner should get happy about this
            if not wait_for_status(runner_name, State.running, timeout=2.0):
                raise RuntimeError(
                    f"{runner_class.__name__} did not switch to running state once "
                    "the websocket server was started."
                )

        # the server has been turned off. The runner should not be happy
        if not wait_for_status(runner_name, State.error, timeout=2.0):
            raise RuntimeError(
                f"{runner_class.__name__} did not switch to error state "
                "when the websocket server was exited."
            )

        # starting the websocket server again
        # can the runner reconnect ?
        with websocket_server(port):
            # the runner should get happy about this
            if not wait_for_status(runner_name, State.running, timeout=2.0):
                raise RuntimeError(
                    f"{runner_class.__name__} did not switch to running state once "
                    "the websocket server has been restarted."
                )

    # second batch of test: the runner is started after the websocket server

    with websocket_server(port) as ws_server:
        _, __, nb_clients = ws_server
        assert nb_clients() == 0

        with get_manager((runner_class, config)):
            # waiting for the runner to have been started by the manager
            wait_for(runner_started, True, args=(runner_name,))
            if not wait_for_status(runner_name, State.running, timeout=2.0):
                raise RuntimeError(
                    f"{runner_class.__name__} did not switch to running state when  "
                    "starting after a websocket server."
                )


class ConfigTester:
    """
    An instance of ConfigTester can be used to generate supported and
    unsupported runner configurations, with the objective to test the behavior
    of a [nightskyrunner.runner.Runner]():
    The runner should be in a "running" state with correct configuration, and
    an "error" state with an incorrect configuration.

    Arguments:
      supported_values: supported configuration, i.e. the related configuration
        should result in the runner being in a 'running' state.
      unsupported_values: unsupported values, i.e. should result in the
        runner being in an 'error' sate. All keys in 'unsupported_values'
        should be in 'supported_values' (otherwise a KeyError is raised).
    """

    def __init__(
        self, supported_values: Config, not_supported_values: Config
    ) -> None:
        self._supported = supported_values
        self._not_supported = not_supported_values
        for key in not_supported_values:
            if key not in supported_values.keys():
                raise KeyError(
                    "ConfigTester: supported_values and not_supported_values "
                    "should have the same set of keys"
                )

    def keys(self) -> set[str]:
        """
        The keys of the 'unsupported_values' configuration.
        """
        return set(self._not_supported.keys())

    def get_config(
        self, unsupported: Union[str, Iterable[str]] = tuple()
    ) -> Config:
        """
        If unsupported is empty, returns the 'supported_values' configuration.
        If unsupported is not empty, returns the 'supported_values' configuration
        except for the unsupported keys for which unsupported values are set.
        """
        if type(unsupported) == str:
            unsupported = (unsupported,)
        for us in unsupported:
            if not us in self._not_supported.keys():
                raise KeyError(f"{us} is not a configuration key")
        r: Config = {}
        for k, v in self._supported.items():
            if k in unsupported:
                r[k] = self._not_supported[k]
            else:
                r[k] = v
        return r

    def set_config(
        self, path: Path, unsupported: Union[str, Iterable[str]] = tuple()
    ) -> None:
        """
        Similar to [ConfigTester.get_config](), except that the configuration
        is written as a toml file.
        """
        c = self.get_config(unsupported=unsupported)
        with tempfile.TemporaryDirectory() as tmp:
            tmp_file = Path(tmp) / "new_config.toml"
            with open(tmp_file, "wb+") as f:
                tomli_w.dump(c, f)
            tmp_file.rename(path)


def _get_status(runner: Union[str, Type[Runner]]) -> str:
    # return a string representation of the status of the runner

    runner_: str
    if type(runner) is Type[Runner]:
        runner = cast(Type[Runner], runner)
        runner_ = runner.__name__
    else:
        runner_ = str(runner)
    return ",".join(
        [f"{k}: {v}" for k, v in Status.retrieve(runner_).get().items()]
    )


def configuration_test(
    runner_class: Type[Runner],
    config_tester: ConfigTester,
    timeout: float = 5.0,
) -> None:
    """
    This function tests that an instance of 'runner_class' is in a
    running state when based on a valid configuration, and in a error state otherwise.
    It also checks it recovers one the configuration error has been fixed.
    """

    runner_name = runner_class.__name__

    with tempfile.TemporaryDirectory() as tmp:
        # setting a correct configuration
        config_file = Path(tmp) / "config.toml"
        config_tester.set_config(config_file)

        with get_manager((runner_class, config_file)):
            # waiting for the runner to start and go into a "running" state
            # (no error because the config is correct)
            if not wait_for_status(
                runner_name, State.running, timeout=timeout
            ):
                raise RuntimeError(
                    f"{runner_class.__name__} did not switch to running state "
                    "when starting with a suitable configuration. "
                    f"State: {_get_status(runner_name)}."
                )

            for config_key in config_tester.keys():
                # setting an incorrect config value for config_key
                config_tester.set_config(config_file, unsupported=config_key)

                # the runner should switch to an error state
                if not wait_for_status(
                    runner_name, State.error, timeout=timeout
                ):
                    raise RuntimeError(
                        f"{runner_class.__name__} did not switch to error state "
                        f"upon unsupported configuration value for key {config_key}. "
                        f"State: {_get_status(runner_name)}."
                    )

                # setting back a correct config
                config_tester.set_config(config_file, unsupported=tuple())

                # runner should return to a "running" state.
                if not wait_for_status(
                    runner_name, State.running, timeout=timeout
                ):
                    raise RuntimeError(
                        f"{runner_class.__name__} did not switch to running state "
                        "when switching back to a suitable configuration. "
                        f"State: {_get_status(runner_name)}."
                    )
