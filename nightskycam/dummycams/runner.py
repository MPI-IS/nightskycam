"""
Module defining DummyCamRunner, a runner which connects to a dummy
camera which generates random images.
"""

from typing import List, Tuple

from nightskyrunner.config import Config
from nightskyrunner.config_getter import ConfigGetter
from nightskyrunner.runner import status_error
from nightskyrunner.wait_interrupts import RunnerWaitInterruptors

from ..cams.runner import CamRunner
from .camera import DummyCamera


@status_error
class DummyCamRunner(CamRunner):
    """
    Takes pictures using a dummy camera. For testing
    purposes.
    """

    def __init__(
        self,
        name: str,
        config_getter: ConfigGetter,
        interrupts: RunnerWaitInterruptors = [],
        core_frequency: float = 1.0 / 0.005,
    ) -> None:
        super().__init__(name, config_getter, interrupts, core_frequency)

    def get_camera(self, active: bool, config: Config) -> Tuple[DummyCamera, List[str]]:
        """
        See [nightskycam.cams.runner.Camera.get_camera][]
        and [nightskycam.dummycams.camera.configure][]
        """
        camera = DummyCamera()
        issues = camera.configure(active, config)
        return camera, issues
