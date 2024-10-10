"""
Module defining the ImageProcessRunner.
"""

import time
from pathlib import Path
from pickle import UnpicklingError
from typing import Any, Dict, List, Optional, Tuple

import nptyping as npt
import numpy as np
import tomli
from nightskycam_serialization.status import ImageProcessRunnerEntries
from nightskyrunner.config import Config
from nightskyrunner.config_error import ConfigError
from nightskyrunner.config_getter import ConfigGetter
from nightskyrunner.runner import ProcessRunner, status_error
from nightskyrunner.status import Level
from nightskyrunner.wait_interrupts import RunnerWaitInterruptors

from ..utils.file_saving import (
    extend_meta,
    get_cv2_config,
    read_files,
    save,
    save_npy,
    supported_file_formats,
)
from .bits_conversion import to_8bits
from .darkframes import darkframes
from .debayer import debayer
from .resize import resize
from .stretch import stretch


class NumpyLoadingError(Exception): ...


def _stretch(
    config: Config, image: npt.NDArray, extra_meta: List[str]
) -> Optional[npt.NDArray]:
    # Reads the config key "stretch" and applies the corresponding
    # stretch method to the image. Update meta with correspondig
    # keys and values.

    try:
        stretch_method = str(config["stretch"])
    except KeyError:
        return None
    if stretch_method is None or stretch_method == "":
        return None
    image = stretch(image, stretch_method)
    extra_meta.append(f"stretching ({stretch_method})")
    return image


class T:
    last_time = None

    @classmethod
    def get(cls) -> float:
        t = time.time()
        if cls.last_time is None:
            cls.last_time = t
            return 0
        else:
            d = t - cls.last_time
            cls.last_time = t
            return d


def _process(
    config: Config, npy_file: Path, meta_file: Path
) -> Tuple[npt.NDArray, str]:
    # Applies all the processing requested by the config to the image
    # saved in npy_file.
    # The meta file is necessary if darkframes are substracted
    # from the image. In this case, the following keys are
    # required in the meta dictionary:
    # - ["controllables"]["Temperature"]
    # - ["controllables"]["Exposure"]
    # Processing are applied in this order:
    # - darkframe substraction
    # - debayer
    # - stretch
    # - resize
    # - eight bits conversion (original is 16 bits)
    # This function returns the processed image, and a
    # string summarizing all the operation that have
    # been applied.

    # reading the image file
    try:
        image = np.load(npy_file, allow_pickle=True)
    except ValueError as e:
        raise NumpyLoadingError(e)
    except UnpicklingError as e:
        raise NumpyLoadingError(e)

    # will be used to list all applied operation
    extra_meta: List[str] = []

    # darkframe substraction
    darkframes_file: Optional[Path]
    try:
        darkframes_file = Path(str(config["darkframes"]))
    except KeyError:
        darkframes_file = None
    if darkframes_file and not darkframes_file.is_file():
        raise FileNotFoundError(
            "requested to perform darkframes substraction, but "
            f"file {darkframes} could not be found"
        )
    if darkframes_file:
        with open(meta_file, "rb") as f:
            meta = tomli.load(f)
        try:
            temperature = int(
                (float(meta["controllables"]["Temperature"]) / 10.0) + 0.5
            )
        except KeyError:
            raise RuntimeError(
                "image processing is configured to substract the darkframes, "
                "but camera temperature information not available in the meta data"
            )
        try:
            exposure = int(meta["controllables"]["Exposure"])
        except KeyError:
            raise RuntimeError(
                "image processing is configured to substract the darkframes, "
                "but camera exposure information not available in the meta data"
            )
        extra_meta.append("darkframe substraction")
        image = darkframes(image, temperature, exposure, darkframes_file)

    # debayer
    # debayer is an empty string or if the "debayer" keys is note
    # in the config, then debayer is not applied
    try:
        if config["debayer"]:
            extra_meta.append(f"debayer with code {config['debayer']}")
            image = debayer(image, conversion_code=str(config["debayer"]))
    except KeyError:
        pass

    # stretching
    stretched = _stretch(config, image, extra_meta)
    if stretched is not None:
        image = stretched

    # resize
    if config["resize"]:
        ratio = float(config["resize"])  # type: ignore
        interpolation = str(config["resize_interpolation"])
        if ratio != 1.0:
            extra_meta.append(
                f"resize with ratio {config['resize']} ({interpolation})"
            )
            image = resize(image, ratio, interpolation=interpolation)

    # 8 bits conversion
    if config["eight_bits"]:
        extra_meta.append("converting to 8bits")
        image = to_8bits(image)

    # listing applied operation as string
    if extra_meta:
        extend_meta(meta_file, {"process": ", ".join(extra_meta)})

    return image, ", ".join(extra_meta)


def _cv2_config(config: Config) -> Optional[Tuple[str, int, int]]:
    # reads config and returns the extra parameters
    # to be passed to opencv when saving the file.
    # If the file is to be saved as Tiff, the parameters
    # will makes sure no compression is applied.
    # If the file is to be saved as jpeg, the parameters
    # will make sure the desired compression (qualility)
    # is applied.
    # The keys read from the config will be "fileformat",
    # and "jpeg_quality".

    try:
        return get_cv2_config(
            str(config["fileformat"]),
            int(config["jpeg_quality"]),  # type: ignore
        )
    except KeyError:
        return get_cv2_config(str(config["fileformat"]))


def _save_files(
    config: Config,
    image: npt.NDArray,
    meta: Dict[str, Any],
    filename: str,
    destination_folder: Path,
) -> None:
    # Save the files (image and toml meta data file).
    # It calls the proper function (save or save_npy)
    # depending on the "fileformat" key of config.
    # It also applies the proper opencv parameters
    # (based on "fileformat" and "jpeg_quality" config keys).

    if str(config["fileformat"]).lower() == "npy":
        save_npy(image, meta, filename, destination_folder)
    else:
        save(
            image,
            destination_folder,
            filename,
            str(config["fileformat"]).lower(),
            _cv2_config(config),
            meta=meta,
        )


@status_error
class ImageProcessRunner(ProcessRunner):
    """
    Runner for processing images (likely taken
    by a [nightskycam.asicams.runner.AsiCamRunner]().
    Depending on the configuration,
    the following processing may be applied:

    - darkframe substraction
    - debayer
    - stretching
    - resizing
    - conversion to 8 bits.

    Configuration keys:

    - source_folder: the folder in which the runner will look for images to process.
      Both npy files (image) and toml files (meta data) are required.
    - destination_folder: the folder to which processed image and updated toml meta data
    - latest_folder: processed images and meta data will be also saved in this folder,
      but overwritting the exiting "latest" image and meta data files.
      files will be saved.
    - darkframes: either the path to a darkframe file, as generated using the
      h5darkframes package, or an empty string (no darkframe substraction).
    - debayer: debayer method as supported by opencv, e.g. "COLOR_BAYER_BG2BGR".
    - stretch: the stretch method: "SqrtStretch", "AsinhStretch" or "auto_stretch"
      or an empty string for no stretching.
    - resize: the factor use to resize the image (e.g. factor 2 will divide the
      width and length by 2). 1.0 for no resize.
    - resize_interpolation: the opencv method used for resize, e.g. "INTER_NEAREST".
    - fileformat: image format used to save the processed image: "tiff", "jpeg" or "npy"
      (npy: image saved as numpy array).

    For darkframe substractiomn, these keys are required in the meta data toml file:

    - ["controllables"]["Temperature"]
    - ["controllables"]["Exposure"]
    """

    def __init__(
        self,
        name: str,
        config_getter: ConfigGetter,
        interrupts: RunnerWaitInterruptors = [],
        core_frequency: float = 1.0 / 0.005,
    ) -> None:
        super().__init__(name, config_getter, interrupts, core_frequency)
        self._nb_processed = 0

    def iterate(self):
        """
        Apply processes to the images found in the source folder
        based on the configuration.
        """

        # reading the toml configuration file
        config = self.get_config()

        # the configuration request the picture to be saved
        # in a non supported file format, exiting with error
        if config["fileformat"].lower() not in supported_file_formats:
            raise ConfigError(
                f"request format ({config['fileformat']}) not supported. "
                f"supported fileformat: {', '.join(supported_file_formats)}"
            )

        # where the images to process are
        source_folder = Path(config["source_folder"])

        # reading the files located in the source folder
        files = read_files(source_folder)

        # the images to process
        try:
            npy_files = files["npy"]
        except KeyError:
            npy_files = []

        # the corresponding meta data files
        try:
            toml_files = files["toml"]
        except KeyError:
            toml_files = []

        for filename in [f for f in toml_files if f not in npy_files]:

            # sometimes a picture is skipped, e.g. because of bad weather.
            # in this case only a toml file is created. Moving this toml
            # file forward, without processing
            # Note: in nightskycam.utils.file_saving, functions save and save_npy,
            # image files are created before meta data toml file.
            origin = source_folder / f"{filename}.toml"
            destination = (
                Path(config["destination_folder"]) / f"{filename}.toml"
            )
            origin.rename(destination)

        for filename in npy_files:
            if filename in toml_files:
                # We process only images that have a proper toml meta data file

                # The image and meta data to process
                self.log(Level.info, f"processing {filename}")
                npy_file = source_folder / f"{filename}.npy"
                meta_file = source_folder / f"{filename}.toml"

                try:
                    # applying all the processes
                    image, process_meta = _process(config, npy_file, meta_file)
                except NumpyLoadingError as e:
                    print("\t\t**process error !", e)
                    self.log(
                        Level.error,
                        f"failed to process {filename}: {e}, deleting",
                    )
                    # corrupted file ! Happens very rarely. Deleting the file
                    # to make sure we do not try to process them again and again.
                    npy_file.unlink()
                    meta_file.unlink()
                    continue

                # saving the processes files ("destination_folder" is likely to
                # be the ftp runner "source_folder")
                with open(meta_file, "rb") as f:
                    meta = tomli.load(f)
                for fname, save_folder in zip(
                    (filename, "latest"),
                    (
                        Path(config["destination_folder"]),
                        Path(config["latest_folder"]),
                    ),
                ):
                    _save_files(config, image, meta, fname, save_folder)

                # deleting processed files
                npy_file.unlink()
                meta_file.unlink()

                # keeping track of the number of processed image
                self._nb_processed += 1

                # sharing status
                self._status.entries(
                    ImageProcessRunnerEntries(
                        number_of_processed_pictures=str(self._nb_processed),
                        processes_applied=process_meta,
                        file_format=config["fileformat"].lower(),
                        last_processed_picture=filename,
                    )
                )

                # one image processed per iteration.
                break
