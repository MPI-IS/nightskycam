"""
Module defining the AsiCamera, the camera used by the AsiCameraRunner.
"""

from typing import Any, Dict, List, Tuple

import nptyping as npt
from camera_zwo_asi import Camera as asi
from camera_zwo_asi import ImageType
from nightskyrunner.config import Config

from ..cams.camera import Camera

_controllables: Tuple[str, ...] = (
    "AutoExpMaxExpMS",
    "AutoExpMaxGain",
    "AutoExpTargetBrightness",
    "BandWidth",
    "CoolerOn",
    "Exposure",
    "Flip",
    "Gain",
    "HighSpeedMode",
    "MonoBin",
    "Offset",
    "TargetTemp",
    "WB_B",
    "WB_R",
)
"""
configuration keys related to the controllables of the camera
(i.e. camera_zwo_asi.Camera.set_control(key,value) should be supported)
"""

_roi: Tuple[str, ...] = (
    "start_x",
    "start_y",
    "width",
    "height",
    "bins",
    "type",
)
"""
configuration keys related to the ROI of the camera
(i.e. setattr(roi, key, value) should be supported
"""


class AsiCamera(Camera):
    """
    Wrapper over camera_zwo_asi.Camera to provide a suitable
    interface to [nightskycam.asicams.runner.AsiCamRunner](AsiCamRunner)
    """

    def __init__(self) -> None:
        self._camera = asi(0)
        self._picture_failed = False

    def is_connected(self) -> bool:
        """
        Returns False if the camera does not
        seems to be properly connected
        """
        try:
            self._camera.get_controls()
        except Exception:
            return False
        return True

    def cooler_on(self) -> None:
        self._camera.set_control("CoolerOn", 1)

    def cooler_off(self) -> None:
        self._camera.set_control("CoolerOn", 0)

    def configure(self, active: bool, config: Config) -> List[str]:
        """
        Configure the camera (controllables and ROI) based on
        [nightskycam.asicams.runner.AsiCamRunner](AsiCamRunner)'s
        configuration. Turn on the cooling if active is True.

        Returns
          List of issues encountered when configuring the camera (empty
          if not issues)
        """
        if not active:
            self.cooler_off()
            return []
        issues: List[str] = []
        for key in _controllables:
            try:
                self._camera.set_control(key, config[key])
            except Exception as e:
                issues.append(
                    f"failed to set configuration {key} to {config[key]}: {e}"
                )
        roi = self._camera.get_roi()
        for key in _roi:
            try:
                if key != "type":
                    setattr(roi, key, config[key])
                else:
                    roi.type = getattr(ImageType, str(config["types"]))
            except Exception as e:
                issues.append(
                    f"failed to set configuration {key} to {config[key]}: {e}"
                )
        try:
            self._camera.set_roi(roi)
        except Exception as e:
            issues.append(f"failed to set ROI: {e}")
        self.cooler_on()
        return issues

    def picture(self) -> Tuple[npt.NDArray, Dict[str, Any]]:
        """
        Takes a picture and returns the corresponding numpy
        array and metadata
        """
        try:
            nimage = self._camera.capture()
        except RuntimeError as e:
            self._picture_failed = True
            raise e
        meta = self._camera.to_dict(specify_auto=False, non_writable=True)
        img = nimage.get_image()
        return img, meta

    def get_info(self) -> Dict[str, str]:
        """
        provides extra information about the camera's state
        (temperature of the camera and if the cooler is on or off).

        Returns:
          keys: "camera_temperature" (float), "camera_target_temperature" (float),
          "cooler_on" (bool).
        """
        controls = self._camera.get_controls()
        return {
            "camera_temperature": controls["Temperature"].value / 10.0,
            "camera_target_temperature": controls["TargetTemp"].value,
            "cooler_on": controls["CoolerOn"].value,
        }
