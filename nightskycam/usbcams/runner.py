"""
Module defining USBCamRunner, 
a subclass of [nightskycam.cams.runner.CamRunner]()
"""

from typing import List, Tuple

from nightskyrunner.config import Config
from nightskyrunner.config_getter import ConfigGetter
from nightskyrunner.runner import status_error
from nightskyrunner.wait_interrupts import RunnerWaitInterruptors

from ..cams.runner import CamRunner
from .camera import USBCamera


@status_error
class USBCamRunner(CamRunner):
    """
    A subclass of [nightskycam.cams.runner.CamRunner]() taking
    pictures from USB cameras.
    """

    def __init__(
        self,
        name: str,
        config_getter: ConfigGetter,
        interrupts: RunnerWaitInterruptors = [],
        core_frequency: float = 1.0 / 0.005,
    ) -> None:
        super().__init__(name, config_getter, interrupts, core_frequency)

    def get_camera(self, active: bool, config: Config) -> Tuple[USBCamera, List[str]]:
        """
        See [nightskycam.cams.runner.Camera.get_camera][]
        and [nightskycam.usbcams.camera.configure][]
        """
        camera = USBCamera()
        issues = camera.configure(active, config)
        return camera, issues
