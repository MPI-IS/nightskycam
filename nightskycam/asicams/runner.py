"""
Module defining AsiCameraRunner.
"""

import re
import subprocess
import time
from typing import List, Optional, Tuple

import usb.core
from nightskyrunner.config import Config
from nightskyrunner.config_getter import ConfigGetter
from nightskyrunner.runner import status_error
from nightskyrunner.wait_interrupts import RunnerWaitInterruptors

from ..cams.runner import CamRunner
from .camera import AsiCamera


def _get_usb_hubs() -> Tuple[str, ...]:
    # this requires uhubctl to be installed:
    # (apt install uhubctl)

    result = subprocess.run(
        ["uhubctl"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    hub_pattern = re.compile(r"Current status for hub (\S+)")
    matches = hub_pattern.findall(result.stdout)
    if not matches:
        raise RuntimeError(
            "AsiZwo camera not detected, and failed to reset "
            "the usb ports using 'uhubctl'"
        )
    return tuple(matches)


def _reset_usb_hubs() -> None:
    # resetting the usb hubs. This is because sometimes
    # the contact with the camera get lost.

    usb_hubs: Tuple[str, ...] = _get_usb_hubs()
    for hub in usb_hubs:
        for status in ("off", "on"):
            subprocess.run(f"uhubctl -l {hub} -a {status}", shell=True)
            time.sleep(1.0)


def _reset_usb(manufacturer_substring: str = "ZWO", first_call: bool = True) -> None:
    # called when the software does not manage to get an handle to the camera:
    # happens sometimes that the usb connection needs to be reset
    # which is what this function does.
    def _is_zwo(device) -> bool:
        try:
            if manufacturer_substring in device.manufacturer:
                return True
        except ValueError:
            return False
        except TypeError:
            return False
        return False

    # listing the usb devices and getting the one corresponding
    # to the camera
    devices = usb.core.find(find_all=True)
    zwo = [device for device in devices if _is_zwo(device)]
    if not zwo:
        # no usb device corresponding to the camera could be found !
        # resetting the full usb hubs.
        if first_call:
            _reset_usb_hubs()
            _reset_usb(manufacturer_substring, first_call=False)
        else:
            raise RuntimeError("failed to detect usb zwo-asi camera")
    # resetting the camera's usb
    zwo[0].reset()


@status_error
class AsiCamRunner(CamRunner):
    """
    CamRunner specific to ASI ZWO usb camera.
    """

    def __init__(
        self,
        name: str,
        config_getter: ConfigGetter,
        interrupts: RunnerWaitInterruptors = [],
        core_frequency: float = 1.0 / 0.005,  # 200Hz
    ) -> None:
        super().__init__(name, config_getter, interrupts, core_frequency)
        self._camera: Optional[AsiCamera] = None

    def on_exit(self):
        """
        turn of the cooler of the camera on exit of the program
        """
        if self._camera:
            self._camera.cooler_off()

    def get_camera(self, active: bool, config: Config) -> Tuple[AsiCamera, List[str]]:
        """
        Returns an instance of AsiCamera, and the list of issues encountered while configuring
        it (empty list of no issue). If the system failed to create an instance of of AsiCamera,
        None is returned instead.
        """
        if self._camera is not None and self._camera._picture_failed:
            self._camera = None
        if self._camera is None:
            _reset_usb()
            self._camera = AsiCamera()
        try:
            issues = self._camera.configure(active, config)
        except Exception as e:
            self._camera = None
            raise e
        return self._camera, issues
