"""
Module defining TestRunner
"""

from typing import Optional

from nightskyrunner.config import Config
from nightskyrunner.config_getter import ConfigGetter
from nightskyrunner.runner import ProcessRunner, status_error
from nightskyrunner.shared_memory import SharedMemory
from nightskyrunner.status import RunnerStatusDict
from nightskyrunner.wait_interrupts import RunnerWaitInterruptors


class StatusTest(RunnerStatusDict, total=False):
    iteration: int
    value: int


@status_error
class TestRunner(ProcessRunner):
    """
    Runner useful for unit-testing.

    Configuration keys:

    - "value": an arbitrary string value
    - "error": if evaluates to True, each iteration
      will raise a RuntimeError.

    An iteration will:

    - read the configuration of "value" and set it in the status
    - increase the value of the attribute "_iteration"
    - share in the status the values of "value" and "_iteration"
    - write in the introspection memory the value of "_iteration"
    - raise a RuntimeError if "error" is True.
    """

    def __init__(
        self,
        name: str,
        config_getter: ConfigGetter,
        interrupts: RunnerWaitInterruptors = [],
        core_frequency: float = 1.0 / 0.005,
    ) -> None:
        super().__init__(name, config_getter, interrupts, core_frequency)
        memory = SharedMemory.get(name)
        memory["error"] = False
        self._iteration: int = 0

    def iterate(self) -> None:
        config = self.get_config()
        try:
            value = int(config["value"])  # type: ignore
        except ValueError:
            value = -1
        except KeyError:
            value = -1
        self._iteration += 1
        self._status.entries(
            StatusTest(iteration=self._iteration, value=value)
        )
        if config["error"]:
            raise RuntimeError("TestRunner configured to raise an error")

    @classmethod
    def default_config(cls) -> Config:
        c: Config = {"frequency": 10.0, "error": False}
        return c
