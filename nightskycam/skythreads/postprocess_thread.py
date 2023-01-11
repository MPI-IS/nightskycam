import toml
import cv2
import time
import typing
import logging
import numpy as np
import multiprocessing
import ctypes
from multiprocessing.synchronize import Lock as LockBase
from pathlib import Path
from ..locks import Locks
from ..cameras import images
from ..types import Configuration
from ..utils import postprocess
from ..skythread import SkyThread
from ..configuration_getter import ConfigurationGetter
from ..types import CV2Format, CV2Params
from ..cameras.get_camera import get_camera

_logger = logging.getLogger("postprocess")


def _get_cv2params(cv2_format: CV2Format) -> CV2Params:
    r: CV2Params = []
    for name, value in cv2_format.items():
        if value != "default":
            try:
                cv2_attr = typing.cast(int, getattr(cv2, name))
            except AttributeError:
                raise AttributeError(
                    "file format configuration error: "
                    f"{name} is not a supported attribute of opencv2"
                )
            r.append(cv2_attr)
            r.append(int(value))
    return r


def _run_postprocess(
    filename: str, config: Configuration, copy_to_latest: bool
) -> None:

    # reading the configuration
    src_dir = Path(config["src_dir"])
    dest_dir = Path(config["dest_dir"])
    latest_dir = Path(config["latest_dir"])
    fileformat = str(config["fileformat"])
    cv2params: CV2Params
    if fileformat != "npy":
        cv2params = _get_cv2params(config[fileformat])
    else:
        cv2params = []

    # the raw image and related toml metadata files
    data_file = src_dir / f"{filename}.npy"
    meta_file = src_dir / f"{filename}.toml"

    # reading the files
    data = np.load(data_file)
    meta = toml.load(meta_file)

    # applying the postprocesses
    postdata = postprocess.apply(data, meta, config, dry_run=False)

    # updating the metadata
    postmeta: Configuration = {}
    for step in config["steps"]:
        postmeta[str(step)] = config[step]
    meta["postprocess"] = postmeta

    # saving the image
    image = images.Image(postdata, meta, filename)
    _logger.info(
        f"saving file {image.filename}.{fileformat} with cv2 parameters {cv2params}"
    )
    image.save(dest_dir, fileformat=fileformat, cv2params=cv2params)
    if copy_to_latest:
        image.filename = "latest"
        image.save(latest_dir, fileformat=fileformat, cv2params=cv2params)

    # deleting the processed files
    data_file.unlink()
    meta_file.unlink()


def _run_all_postprocesses(
    config: Configuration, copy_to_latest: bool
) -> typing.Tuple[int, int]:

    # reading the configuration
    src_dir = Path(config["src_dir"])
    batch_size = int(config["batch_size"])

    # all dumped image numpy array
    data_files = list(src_dir.glob("*.npy"))

    # number of files that are waiting for postprocess
    nb_files = len(data_files)

    # we deal now only up to batch size files
    data_files = data_files[:batch_size]

    # processing them one by one ...
    for df in data_files:
        # but only if there is already a related
        # metadata file
        metafile = src_dir / f"{df.stem}.toml"
        if metafile.is_file():
            # applying the postprocess and
            # writing the files in dest_dir
            _run_postprocess(df.stem, config, copy_to_latest)

    # returning number of files processed and number of file remaining
    processed = len(data_files)
    remaining = nb_files - processed
    return processed, remaining


class _Process:
    def __init__(
        self,
        config: ConfigurationGetter,
        lock: LockBase,
        sleep: float = 0.2,
        copy_to_latest: bool = True,
        error_length: int = 1000,
    ) -> None:
        self._config = config
        self._lock = lock
        self._running = multiprocessing.Value("i", False)
        self._processed = multiprocessing.Value("i", 0)
        self._remaining = multiprocessing.Value("i", 0)
        self._error_message = multiprocessing.Array("c", str.encode(" " * error_length))
        self._error_length = error_length
        self._sleep = sleep
        self._process: typing.Optional[multiprocessing.Process] = None
        self._copy_to_latest = copy_to_latest

    def _run(self) -> None:
        self._running.value = True
        while self._running.value:
            try:
                config = self._config.get("PostprocessThread")
            except Exception as e:
                error = f"configuration error: {e}"
                error = error[: self._error_length]
                self._error_message.value = str.encode(error)
                break
            try:
                processed, remaining = _run_all_postprocesses(
                    config, self._copy_to_latest
                )
                self._processed.value += processed
                self._remaining.value = remaining
            except Exception as e:
                error = f"processing error: {e}"
                error = error[: self._error_length]
                self._error_message.value = str.encode(error)
                break
            time.sleep(self._sleep)

    def get_error(self) -> str:
        error = self._error_message.value.decode()
        return error

    def alive(self) -> bool:
        if self._process is None:
            return False
        return self._process.is_alive()

    def get_stats(self) -> typing.Tuple[int, int]:
        return self._processed.value, self._remaining.value

    def start(self) -> None:
        self._process = multiprocessing.Process(target=self._run)
        self._process.start()

    def stop(self) -> None:
        if self._process is not None:
            self._running.value = False
            self._process.join()
            self._process = None
            self._exception = None

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, _, __, ___):
        self.stop()


class PostprocessThread(SkyThread):
    def __init__(self, config_getter: ConfigurationGetter):
        super().__init__(config_getter, "postprocess")
        self._process: typing.Optional[_Process] = None

    @classmethod
    def check_config(cls, config_getter: ConfigurationGetter) -> typing.Optional[str]:

        # reading the configuration file
        config: Configuration = config_getter.get("PostprocessThread")

        # src_dir: where the images to process will be located
        # dest_dir: where the processed images will be saved
        # latest_dir: where the processed images will be saved (but with generic name)
        pathkeys = ("src_dir", "dest_dir", "latest_dir")
        # checking the configuration values exist
        for pathkey in pathkeys:
            try:
                config[pathkey]
            except KeyError:
                return f"failed to find the required key '{pathkey}'"
        # checking the directories exists, creating them if required
        for pathkey in pathkeys:
            try:
                Path(config[pathkey]).mkdir(parents=True, exist_ok=True)
            except Exception as e:
                return str(
                    f"the path provided for {pathkey} does not exists and "
                    f"could not be created: {e}"
                )

        # format in which the final images should be saved
        # (e.g. 'tiff', 'jpeg')
        try:
            fileformat = config["fileformat"]
        except KeyError:
            return "failed to find the required key 'fileformat'"

        # the selected format should also have its own configuration
        # values (except if saving as numpy array)
        if fileformat != "npy":
            try:
                config[fileformat]
            except KeyError:
                return str(
                    f"the configuration for the selected fileformat {fileformat} "
                    "could not be found"
                )

        # the list of postprocesses to apply
        try:
            steps = config["steps"]
        except KeyError:
            return "failed to find the required key 'steps'"
        if not isinstance(steps, list):
            return "the value for the key 'steps' should be a list"

        # checking all postprocess step is known
        postprocesses = [
            k for k in config.keys() if not k in ("steps", "fileformat", "batch_size")
        ]
        for step in steps:
            if step not in postprocesses:
                return str(
                    f"the postprocess {step} is required by steps "
                    f"({str(steps)}) but has no related configuration key"
                )

        # batch size for processing files
        try:
            batch_size = config["batch_size"]
        except KeyError:
            return "failed to find the required key 'batch_size'"
        try:
            int(batch_size)
        except ValueError as e:
            return (
                f"failed to cast to int the value of 'batch_size' ({batch_size}): {e}"
            )

        # everything ok !
        return None

    def deploy_test(self) -> None:

        # getting the configuration
        config = self._config_getter.get("PostprocessThread")

        # connecting to the camera and taking
        # a test picture
        try:
            camera, classname = get_camera(self._config_getter)
        except NotImplementedError:
            # no picture thread setup in the configuration,
            # so the PostprocessThread can not be tested.
            # exit
            return

        camera_config = self._config_getter.get(classname)

        if "Exposure" in camera_config:
            camera_config["Exposure"] = 1000

        camera.active_configure(camera_config)
        image = camera.picture()

        # filename for the picture and the metadata
        filename: str = "deploy_test"

        # saving the picture to the directory
        # postprocess thread will look at
        image.save(Path(config["src_dir"]), fileformat="npy", filename=filename)

        # starting the postprocess process
        time_start = time.time()
        timeout = 5.0
        with _Process(
            self._config_getter, Locks.get_config_lock(), copy_to_latest=False
        ) as p:
            while True:
                treated, _ = p.get_stats()
                if treated >= 1:
                    break
                error = p.get_error().strip()
                if error:
                    raise RuntimeError(error)
                if time.time() - time_start > timeout:
                    raise RuntimeError(
                        "postprocess failed: no image file created after a timeout "
                        f"of {timeout}s"
                    )
                time.sleep(0.01)

        # checking the final files are where they are expected
        final_testfile = Path(config["dest_dir"]) / f"{filename}.{config['fileformat']}"
        final_metafile = Path(config["dest_dir"]) / f"{filename}.toml"

        if not final_testfile.is_file():
            raise FileNotFoundError(
                f"failed to find the image file the postprocessing thread should "
                f"have generated ({final_testfile})"
            )

        if not final_metafile.is_file():
            raise FileNotFoundError(
                f"failed to find the image file the postprocessing thread should "
                f"have generated ({final_testfile})"
            )

        final_testfile.unlink()
        final_metafile.unlink()

    def on_exit(self) -> None:
        if self._process is not None:
            self._process.stop()
            self._process = None

    def _execute(self) -> None:

        if self._process is None:
            self._process = _Process(
                self._config_getter, Locks.get_config_lock(), copy_to_latest=True
            )
            self._process.start()
            config = self._config_getter.get("PostprocessThread")
            self._status.set_misc("file format", str(config["fileformat"]))
            self._status.set_misc("steps", ", ".join([str(s) for s in config["steps"]]))

        else:
            try:
                error = self._process.get_error().strip()
            except Exception as e:
                error = f"failed to decode error: {e}"
            if error:
                self._process.stop()
                self._process = None
                raise Exception(error)
            if not self._process.alive():
                self._process = None
                raise ValueError(
                    "the postprocess thread stopped running (reason unknown)"
                )
            treated, remaining = self._process.get_stats()
            self._status.set_misc("treated", str(treated))
            self._status.set_misc("remaining", str(remaining))

        time.sleep(0.5)
