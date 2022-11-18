import toml
import cv2
import time
import typing
import logging
import numpy as np
import multiprocessing
from multiprocessing.synchronize import Lock as LockBase
from pathlib import Path
from ..locks import Locks
from ..cameras import images
from ..types import Configuration
from ..utils import postprocess
from ..skythread import SkyThread
from ..configuration_getter import ConfigurationGetter
from ..types import CV2Format, CV2Params


logger = logging.getLogger("postprocess")


def _get_cv2params(cv2_format: CV2Format) -> CV2Params:
    r: CV2Params = []
    for name, value in cv2_format.items():
        if value != "default":
            try:
                cv2_attr = getattr(cv2, name)
            except AttributeError:
                raise AttributeError(
                    "file format configuration error: "
                    f"{name} is not a supported attribute of opencv2"
                )
            r.append((cv2_attr, int(value)))
    return r


def _run_postprocess(
    filename: str,
    config: Configuration,
) -> None:

    # reading the configuration
    src_dir = Path(config["src_dir"])
    dest_dir = Path(config["dest_dir"])
    fileformat = str(config["fileformat"])
    cv2params = _get_cv2params(config[fileformat])

    # the raw image and related toml metadata files
    data_file = src_dir / f"{filename}.npy"
    meta_file = src_dir / f"{filename}.toml"

    # reading the files
    data = np.load(data_file)
    meta = toml.load(meta_file)

    # applying the postprocesses
    postdata = postprocess.apply(data, config, dry_run=False)

    # updating the metadata
    postmeta: Configuration = {}
    for step in config["steps"]:
        postmeta[str(step)] = config[step]
    meta["postprocess"] = postmeta

    # saving the image
    image = images.Image(postdata, postmeta, filename)
    image.save(dest_dir, fileformat=fileformat, cv2params=cv2params)


def _run_all_postprocesses(config: Configuration) -> typing.Tuple[int, int]:

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
            _run_postprocess(df.stem, config)

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
    ) -> None:
        self._config = config
        self._lock = lock
        self._running = multiprocessing.Value("i", False)
        self._processed = multiprocessing.Value("i", 0)
        self._remaining = multiprocessing.Value("i", 0)
        self._sleep = sleep
        self._process: typing.Optional[multiprocessing.Process] = None

    def _run(self) -> None:
        self._running.value = True
        while self._running.value:
            config = self._config.get("PostprocessThread")
            processed, remaining = _run_all_postprocesses(config)
            self._processed.value += processed
            self._remaining.value = remaining
            time.sleep(self._sleep)

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
        pathkeys = ("src_dir", "dest_dir")
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
        # values
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
        postprocesses = [v for v in config.values() if not v == "steps"]
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

        # creating a dummy image in the postprocess directory
        filename = "deploy_test"
        testfile = Path(config["src_dir"]) / f"{filename}.npy"
        metafile = Path(config["src_dir"]) / f"{filename}.toml"
        data = np.zeros((200, 400))
        np.save(testfile, data)
        metadata = {"type": "deploy test file"}
        with open(metafile, "w") as f:
            toml.dump(metadata, f)

        # starting the postprocess process
        time_start = time.time()
        timeout = 5.0
        with _Process(self._config_getter, Locks.get_config_lock()) as p:
            while True:
                treated, _ = p.get_stats()
                if treated >= 1:
                    break
                if time.time() - time_start > timeout:
                    raise RuntimeError(
                        "postprocess failed: no image file created after a timeout "
                        f"of {timeout}s"
                    )

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

    def on_exit(self) -> None:
        if self._process is not None:
            self._process.stop()
            self._process = None

    def _execute(self) -> None:

        if self._process is None:
            self._process = _Process(self._config_getter, Locks.get_config_lock())
            self._process.start()
            config = self._config_getter.get("PostprocessThread")
            self._status.set_misc("file format", str(config["fileformat"]))
            self._status.set_misc("steps", ", ".join([str(s) for s in config["steps"]]))

        else:
            treated, remaining = self._process.get_stats()
            self._status.set_misc("treated", str(treated))
            self._status.set_misc("remaining", str(remaining))

        time.sleep(0.5)
