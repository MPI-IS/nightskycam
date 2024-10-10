"""
Module defining the virtual Camera superclass.
"""

from typing import Dict, List, Protocol, Tuple

import numpy
from nightskyrunner.config import Config


class Camera(Protocol):
    """
    Subclasses of [nightskycam.cams.runner.CamRunner]() will use
    an implementation of this Protocol to take pictures.
    """

    def configure(self, active: bool, config: Config) -> List[str]:
        """
        Setup the configuration of the camera.

        Arguments:
          active: if True, the camera is currently taking pictures, otherwise
            the camera is inactive.
          config: arbitrary configuration dictionary.
        """
        ...

    def picture(self) -> Tuple[numpy.ndarray, dict]:
        """
        Capture a picture and return it.
        """
        ...

    def is_connected(self) -> bool:
        """
        Should return False if the camera is not connected.
        (This will result in the [nightskycam.cams.runner.CamRunner]()
        instance to raise a RuntimeError).
        """
        ...

    def get_info(self) -> Dict[str, str]:
        """
        Returns meta data related to the camera state.
        (The [nightskycam.cams.runner.CamRunner]()
        will add this data to the toml meta data file associated
        with pictures).
        """
        ...
