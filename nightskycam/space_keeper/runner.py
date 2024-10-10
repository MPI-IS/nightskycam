"""
Module defining SpaceKeeperRunner.
"""

import os
import pathlib
from pathlib import Path

from nightskycam_serialization.status import SpaceKeeperRunnerEntries
from nightskyrunner.config_getter import ConfigGetter
from nightskyrunner.runner import ThreadRunner, status_error
from nightskyrunner.status import Level
from nightskyrunner.wait_interrupts import RunnerWaitInterruptors

from .utils import (
    bits_to_human,
    convert_mb_to_bits,
    DiskSpaceInfo,
    disk_space_info,
    disk_space_info_str,
    files_to_delete,
    folder_content,
    to_GB,
)


@status_error
class SpaceKeeperRunner(ThreadRunner):
    """
    Runner that ensures the system does not get out of space by deleting
    the oldest files of a given directory.

    At each iteration, the remaining space left on the "main" disk
    (i.e. the one on which "/" is mounted) is evaluated using the disk_usage
    function from the psutil package. If the space left is below
    a given threshold, the required number of files
    contained by the given directory are deleted, deleting older files first.

    Usually, this runner will be configured to delete files from the ftp
    folder. This is because it is preferable to looe some pictures rather
    than getting out of disk space, which can make the system unusable.

    Most likely, deleting of images will occur when the system looses internet
    connections for a few days. When this happens, the system may take pictures
    while failing to upload them, resulting in decreasing of available space.

    Configuration keys:

    - "folder": the folder from which files will be deleted

    - "threshold_MB": the threshold of available disk space below which
      data will be deleted.

    """

    def __init__(
        self,
        name: str,
        config_getter: ConfigGetter,
        frequency: float = 1.0,
        interrupts: RunnerWaitInterruptors = [],
        core_frequency: float = 1.0 / 0.005,
    ) -> None:
        super().__init__(name, config_getter, interrupts, core_frequency)
        self._nb_deleted: int = 0

    def iterate(self):

        # reading this runner toml config file
        config = self.get_config()
        folder = pathlib.Path(config["folder"])
        threshold_MB = int(config["threshold_MB"])  # type: ignore

        # invalid configuration, exit with error
        if threshold_MB <= 0:
            raise ValueError(
                "configured with the invalid negative threshold value "
                f"{threshold_MB}"
            )

        # checking disk space information
        disk_info: DiskSpaceInfo = disk_space_info(folder)

        # informing users of the disk space status
        files, folder_size = folder_content(folder)
        if files:
            files_listing = "\n" + "\n".join(
                [
                    f"{ext.removeprefix('.')}: {nb_files} files"
                    for ext, nb_files in files.items()
                ]
            )
        else:
            files_listing = ""

        # if disk is too full, to_delete will list the files to
        # delete
        to_delete = files_to_delete(
            Path(folder), convert_mb_to_bits(threshold_MB)
        )

        self._status.entries(
            SpaceKeeperRunnerEntries(
                folder=f"content size: {bits_to_human(folder_size)}{files_listing}",
                disk=disk_space_info_str(disk_info),
                threshold=bits_to_human(convert_mb_to_bits(threshold_MB)),
                free_space=to_GB(bits_to_human(disk_info["free_space"])),
                deleting=len(to_delete) > 0,
            )
        )

        # deleting files (if any)
        if to_delete:
            self.log(Level.info, f"deleting {len(to_delete)} files")
            self._status.activity("deleting files")
            list(map(os.remove, to_delete))
            self._nb_deleted += len(to_delete)
            self._status.value("number of deleted files", self._nb_deleted)
