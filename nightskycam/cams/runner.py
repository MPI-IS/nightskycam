"""
Module defining the CamRunner superclass.
CamRunner is an abstract class for runner connecting to a camera
for taking pictures.

See:

- [nightskycam.asicams.runner.AsiCamRunner](): for zwo-asi cameras
- [nightskycam.usbcams.runner.UsbCamRunner](): for usb webcams
- [nightskycam.dummycams.runner.DummyCamRunner](): virtual camera for 
    creating artificial images, for testing
"""

import datetime
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from nightskycam_serialization.status import CamRunnerEntries
from nightskyrunner.config import Config
from nightskyrunner.config_getter import ConfigGetter
from nightskyrunner.runner import ProcessRunner, status_error
from nightskyrunner.shared_memory import SharedMemory
from nightskyrunner.status import Level
from nightskyrunner.wait_interrupts import RunnerWaitInterruptors

from ..location_info.runner import LocationInfoRunner
from ..utils.file_saving import save_meta, save_npy
from ..utils.filename import get_filename
from .camera import Camera
from .utils import get_local_info, is_active, read_config, time_window_str


@status_error
class CamRunner(ProcessRunner):
    """
    Runner for taking pictures when "suitable" to do so.

    Configuration keys:

    - start_time (formatted: "%H:%M")
    - end_time (formatted: "%H:%M")
    - use_sun_alt (bool)
    - use_weather (bool)
    - cloud_cover_threshold (int between 0 and 100)
    - nightskycam: name of the system on which the runner is executed
    - frequency: frequency at which pictures will be taken (in Hz)
    - destination_folder : folder in which images will be saved
    - pause (bool): if true, no picture should be taken

    Pictures will not be taken when:

    - use_weather is True and the current cloud cover is above
      cloud_cover_threshold.
    - pause is true

    Pictures will be taken when:

    - use_sun_alt is true and it is currently night
    - use_sun_alt is False and the current time is between start_time
      and end_time

    The runner will read the current states "night" and "cloud_cover"
    from the shared memory. Data in the shared memory is filled by
    an instance of [nightskycam.location_info.runner.LocationInfoRunner]().
    If no instance of LocationInfoRunner is running (or if one is running
    but fails to fetch the data from internet), then the runner will behave
    the same is if use_sun_alt and use_weather are False.

    When pictures are taken, they are taken at the specified frequency.
    Between pictures, the runner will sleep in a manner such that all
    runners iterating at the same frequency will take a picture at the same
    time, assuming the systems on which they run have clock synchronization
    (e.g. via Network Time Protocol).
    """

    def __init__(
        self,
        name: str,
        config_getter: ConfigGetter,
        interrupts: RunnerWaitInterruptors = [],
        core_frequency: float = 1.0 / 0.005,  # 200Hz
    ) -> None:
        super().__init__(name, config_getter, interrupts, core_frequency)
        SharedMemory.get(LocationInfoRunner.sm_key)
        self._nb_pictures = 0
        self._last_picture_filename = ""

    @staticmethod
    def _wait_duration(
        frequency: float, now: datetime.time
    ) -> Tuple[float, float]:
        period = 1.0 / frequency
        now_seconds = (
            now.hour * 3600
            + now.minute * 60
            + now.second
            + now.microsecond * 1e-6
        )
        nb_pictures_since_midnight = int(now_seconds / period)
        next_picture_time = period * (nb_pictures_since_midnight + 1)
        sleep_time = max(0, next_picture_time - now_seconds)
        return next_picture_time, sleep_time

    def wait(self, now: Optional[datetime.time] = None) -> None:
        """
        Overload of the Runner's [nightskyrunner.runner.wait][wait]
        method that ensures that all active cameras (i.e. cameras from
        different systems) take pictures at the same time if their 'frequency'
        is set to the same value (and their host clocks are synchronized).
        """

        frequency = float(self.get_config()["frequency"])  # type: ignore
        if frequency <= 0.0:
            raise ValueError("Negative or null frequency is not supported")

        if now is None:
            now = datetime.datetime.now().time()

        _, sleep_time = self._wait_duration(frequency, now)
        sleep_start = time.time()
        while time.time() - sleep_start < sleep_time:
            try:
                for interrupt in self._interrupts:
                    if interrupt():
                        return
                time.sleep(1.0 / self._core_frequency)
            except KeyboardInterrupt:
                self._keyboard_interrupted = True
                break

    def _update_status(
        self,
        frequency: float,
        active: bool,
        reason: str,
        start: datetime.time,
        end: datetime.time,
        use_sun_alt: bool,
        use_weather: bool,
        night: Optional[bool],
        cloud_cover: Optional[int],
        cloud_cover_threshold: int,
        weather: Optional[str],
        config_issues: List[str],
        cam_info: Dict[str, str],
        pause: bool,
    ) -> None:

        status_dict = CamRunnerEntries()

        # during which time window period pictures are taken
        status_dict["time_window"] = time_window_str(start, end)

        # if the sun altitude is used to determine if day or night
        status_dict["use_sun_alt"] = use_sun_alt

        # if pictures are skipped when bad weather
        status_dict["use_weather"] = use_weather

        # if the runner is currently active or not, and why
        # (active: currently taking pictures)
        status_dict["active"] = f"{'yes' if active else 'no'} - {reason}"

        # report issue: should use sun altitude, but the sun altitude
        # is not available
        issues: List[str] = []
        if use_sun_alt and night is None:
            issues.append(
                "should use sun altitude, but information not available"
            )

        # report issue: should use weather, but weather information not available
        if use_weather and cloud_cover is None:
            issues.append(
                "should use sun weather, but information not available"
            )

        # period at which pictures are taken
        period = 1.0 / frequency
        status_dict["picture"] = f"every {period:.2f} second(s)"

        # name of the latest picture taken
        status_dict["latest_picture"] = self._last_picture_filename

        # number of pictures taken since this runner started
        status_dict["number_of_pictures_taken"] = self._nb_pictures

        # misc information about the status of the camera
        status_dict["camera_info"] = cam_info

        # is the camera pausing ?
        # (may happen when the website users
        # is visiting the 'snapshots' interface)
        status_dict["pause"] = pause

        # managing issues
        for config_issue in config_issues:
            issues.append(config_issue)
        if issues:
            for issue in issues:
                self.log(Level.warning, issue)
            issue_str = "\n".join(issues)
            self._status.set_issue(issue_str)
        else:
            self._status.remove_issue()

        # sharing the status dictionary
        self._status.entries(status_dict)

    def get_camera(
        self, active: bool, config: Config
    ) -> Tuple[Camera, List[str]]:
        """
        Arguments
          active: true if the camera will need to take picture
          config: configuration of the camera

        Returns:
          A tuple:
          - an instance of [nightskycam.cams.runner.Camera][Camera]
          - the list of issues encountered when instantiating the camera
        """
        raise NotImplementedError()

    def iterate(self):
        """
        Evaluate if the camera should be active at this given time
        and given weather, and if so take a picture.
        """

        # read the toml configuration file
        config = self.get_config()
        (
            start,
            end,
            use_sun_alt,
            use_weather,
            cloud_cover_threshold,
            system_name,
            frequency,
            pause,
        ) = read_config(config)

        # read in the shared memory data written by
        # LocalInfoRunner. night, weather and cloud_cover
        # will be None if no instance of LocalInfoRunner
        # is running, or if there is no internet connection.
        night, weather, cloud_cover = get_local_info()

        # "decides" if now is a good time to take picture, based
        # on the configuration, the weather and the sun altitude.
        # active: if the camera should take picture
        # reason: insight why active is True or False
        #   (e.g. 'day time')
        # bad_weather: if active is False, bad_weather will
        #   be True if the reason is a high cloud coverage value.
        #   (in this case a toml meta data file will be created and
        #   uploaded to the server, so users can know how many pictures
        #   have been skipped because of bad weather).
        active, reason, bad_weather = is_active(
            start,
            end,
            use_sun_alt,
            use_weather,
            night,
            cloud_cover,
            cloud_cover_threshold,
            weather,
            datetime.datetime.now().time(),
            pause,
        )

        # getting the camera.
        # Note: we get the camera even if no picture is to be taken,
        # as we may need to configure the camera when inactive. E.g.
        # the cooler of ASI ZWO camera is turned off when no picture
        # is taken.
        camera, config_issues = self.get_camera(active, config)

        # meta data to add to the meta data toml file and to the
        # introspection data.
        camera_info = camera.get_info()
        meta = {}

        # connection to the camera is lost !
        if not camera.is_connected():
            raise RuntimeError("the camera does not seem to be connected")

        if bad_weather:
            # bad weather means that pictures are not taken because
            # of cloud coverage. We create a toml meta data file
            # that will give this information to users.
            self.log(
                Level.info,
                f"skipping picture: {str(weather).lower()}",
            )
            filename = get_filename(system_name)
            save_meta(
                {
                    "weather": str(weather).lower(),
                    "cloud_cover": cloud_cover,
                },
                filename,
                Path(config["destination_folder"]),
            )

        else:
            if active:
                # Camera is active: taking picture and creating
                # corresponding numpy image file (and toml meta data
                # file).
                self._status.activity("taking picture")
                self.log(Level.info, "taking picture")
                img, meta = camera.picture()
                if weather:
                    meta["weather"] = str(weather).lower()
                if cloud_cover:
                    meta["cloud_cover"] = cloud_cover
                    if use_weather:
                        meta["cloud_cover_threshold"] = cloud_cover_threshold
                filename = get_filename(system_name)
                self._status.activity("saving file")
                save_npy(
                    img,
                    meta,
                    filename,
                    Path(config["destination_folder"]),
                )
                self._nb_pictures += 1

        # The status of this runner is quite complicated...
        self._update_status(
            frequency,
            active,
            reason,
            start,
            end,
            use_sun_alt,
            use_weather,
            night,
            cloud_cover,
            cloud_cover_threshold,
            weather,
            config_issues,
            camera_info,
            pause,
        )
