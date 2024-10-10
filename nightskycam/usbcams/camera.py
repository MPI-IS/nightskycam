"""
Module defining USBCamera, a subclass 
of [nightskycam.cams.camera.Camera]()
"""

import os
from multiprocessing import Pipe, Process
from multiprocessing.connection import Connection
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np
from nightskyrunner.config import Config

from ..cams.camera import Camera


def _get_camera(inverse: bool) -> Optional[cv2.VideoCapture]:
    # Each USB camera is given an index by the OS.
    # This function detects plugged cameras by "swapping"
    # indices between 0 and 100. It then returns the camera
    # corresponding to the lowest index (if inverse is False)
    # or to the highest index (otherwise)

    def _get_index(inverse: bool, connection: Connection) -> None:
        range_args: Tuple[int, ...]
        if inverse:
            range_args = (100, -1, -1)
        else:
            range_args = (100,)
        for index in range(*range_args):
            # checking if this index corresponds to a
            # plugged camera. I could not find any
            # other method than simply trying to connect
            # and see if it works out.
            camera = cv2.VideoCapture(index)
            if camera.isOpened():
                camera.release()
                connection.send(index)
                connection.close()
                return
        connection.send(None)
        connection.close()

    def _get_index_no_std(inverse: bool, connection: Connection) -> None:
        with open(os.devnull, "w") as fp:
            # _get_index will try to access all possible indices for USB cams, which
            # will generate a lot of reports printed in the
            # stdout and stderr. Here disabling stdout and stderr.
            os.dup2(fp.fileno(), os.sys.stdout.fileno())  # type: ignore
            os.dup2(fp.fileno(), os.sys.stderr.fileno())  # type: ignore
            _get_index(inverse, connection)

    parent_connection, child_connection = Pipe()
    p = Process(target=_get_index_no_std, args=(inverse, child_connection))
    p.start()
    index: Optional[int] = parent_connection.recv()
    p.join()
    if index:
        return cv2.VideoCapture(index)
    return None


def get_first_camera_index() -> Optional[cv2.VideoCapture]:
    """
    Returns the USB camera with the lowest index.
    """
    return _get_camera(False)


def get_last_camera_index() -> Optional[cv2.VideoCapture]:
    """
    Returns the USB camera with the highest index.
    """
    return _get_camera(True)


class USBCamera(Camera):
    """
    Subclass of [nightskycam.cams.camera.Camera] for taking
    pictures via USB cameras.
    """

    def __init__(self) -> None:
        self._camera: Optional[cv2.VideoCapture] = None
        self._applied_config: Dict[str, str] = {}

    def configure(self, active: bool, config: Config) -> List[str]:
        """
        Configuration keys:

        - cam_index: If an int, the instance will connect to the camera of the provided
          index. If (the string) "first", it will connect to the camera of lowest index,
          and if "last" to the camera with the highest index.
        """

        issues: List[str] = []
        if "cam_index" not in config.keys():
            self._camera = cv2.VideoCapture(0)
        elif config["cam_index"] == "first":
            self._camera = get_first_camera_index()
        elif config["cam_index"] == "last":
            self._camera = get_last_camera_index()
        else:
            self._camera = cv2.VideoCapture(
                int(config["cam_index"])
            )  # type: ignore
        if self._camera is None or not self._camera.isOpened():
            self._camera = None
            return ["failed to connect to the camera"]
        for k, v in config.items():
            if k in dir(cv2):
                try:
                    self._camera.set(getattr(cv2, k), int(v))  # type: ignore
                    self._applied_config[k] = str(v)
                except (TypeError, NameError) as e:
                    issues.append(
                        f"failed to set config {k} to value {v}: {e}"
                    )
        return issues

    def picture(self) -> Tuple[np.ndarray, dict]:
        if self._camera is None:
            raise RuntimeWarning("camera not connected")
        ret, frame = self._camera.read()
        if not ret:
            raise RuntimeError("failed to take picture")
        self._camera.release()
        self._camera = None
        rconfig = {k: v for k, v in self._applied_config.items()}
        self._applied_config = {}
        return frame, rconfig

    def is_connected(self) -> bool:
        return self._camera is not None and self._camera.isOpened()

    def get_info(self) -> Dict[str, str]:
        """
        Returns an empty dictionary.
        """
        return {}
