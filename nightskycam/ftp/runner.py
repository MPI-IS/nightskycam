"""
Module for the Ftp Runner
"""

import time
from collections import deque
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from nightskycam_serialization.status import FtpRunnerEntries
from nightskyrunner.config import Config
from nightskyrunner.config_getter import ConfigGetter
from nightskyrunner.runner import ThreadRunner, status_error
from nightskyrunner.status import Level
from nightskyrunner.wait_interrupts import RunnerWaitInterruptors

from ..utils.filename import sort_by_night
from ..utils.formating import bits_to_human
from ..utils.folder_stats import list_nb_files
from .ftp import FtpConfig, get_ftp


def _get_remote_dir(remote_subdir: str, date: str, system_name: str) -> Path:
    """
    Returns
    remote_subdir / hostname / date /
    """
    return Path(remote_subdir) / system_name / date


def _get_ftp_config(config: Config) -> FtpConfig:
    """
    Returns an instance of FtpConfig based on the
    user's configuration.
    """
    remote_subdir_: Optional[str]
    remote_subdir: Optional[Path]
    try:
        remote_subdir_ = str(config["remote_subdir"])
    except KeyError:
        remote_subdir_ = None
    if remote_subdir_ in ("None", ""):
        remote_subdir = None
    else:
        remote_subdir = Path(str(remote_subdir_))
    return FtpConfig(
        str(config["username"]),
        str(config["password"]),
        str(config["host"]),
        int(config["port"]),  # type: ignore
        folder=remote_subdir,
    )


class _UploadSpeed:
    def __init__(self, memory_in_sec=60 * 60) -> None:
        self._q: deque[Tuple[float, float]] = deque()
        self._memory_in_sec = memory_in_sec

    def add(self, uploaded_size: float, now: Optional[float] = None) -> None:
        if now is None:
            now = time.time()
        self._q.append((now, uploaded_size))

    def get(self, now: Optional[float] = None) -> float:
        if now is None:
            current = time.time()
        else:
            current = now
        try:
            # Delete values that are too old for memory.
            while current - self._q[0][0] > self._memory_in_sec:
                self._q.popleft()
        except ValueError:
            pass
        except IndexError:
            pass
        try:
            time_diff = self._q[-1][0] - self._q[0][0]
        except IndexError:
            return 0.0
        if time_diff == 0.0:
            return 0.0
        return sum([v[1] for v in self._q]) / time_diff


@status_error
class FtpRunner(ThreadRunner):
    """
    Runner than uploads images and toml meta data files to
    a remote ftp server.

    Configuration keys:

    - host: of the ftp server
    - port: of the ftp server
    - username: for ftp connection
    - password: for ftp connection
    - source_folder: location of the files to upload
    - remote_subdir: files will be uploaded to
      this subfolder on the remote ftp server
    - nightskycam: name of the nightskycam system
      on which the runner is deployed
    - batch: maximum number of files which will be uploaded
      per runner iteration

    At each iteration, files in source_folder are listed:

    - only files which name are "date formated" (i.e.
      in format "system_name_YY_MM_DD_HH_MM_SS") are taken into account
      (see [nightskycam.utils.filename.is_date_filename]()).
    - if there are files to download, a new ftp connection is created and
      the "batch" newer files are uploaded ("batch", see configuration
      keys right above)

    Files are uploaded to the following subfolders on the remote ftp server:
    '<root> / remote_subdir / nightskycam_name / date' (date as read from
    the name of the file being uploaded).

    To select a value for "batch":

    - high values of "batch" will allow to upload more file per
      ftp connection, which is more efficient
    - hight values of "batch" implies a nightskycam system may take
      more time to shutdown as the batch will first finish to upload.

    Values between 2 and 10 are adviced.
    """

    def __init__(
        self,
        name: str,
        config_getter: ConfigGetter,
        interrupts: RunnerWaitInterruptors = [],
        core_frequency: float = 1.0 / 0.005,
    ) -> None:
        super().__init__(
            name,
            config_getter,
            interrupts,
            core_frequency,
            stop_priority=10,
        )
        self._nb_files: Dict[str, int] = {}
        # tracking the number of GB uploaded since the runner started
        # (will be added to status)
        self._uploaded_size: int = 0
        # tracking the upload speed
        self._upload_speed = _UploadSpeed()

    def _update_status(
        self, files: List[Path], uploaded_size: int, local_dir: Path
    ) -> None:
        # write in the runner status the number of uploaded files and the
        # total uploaded size.

        for f in files:
            try:
                self._nb_files[f.suffix[1:]] += 1
            except KeyError:
                self._nb_files[f.suffix[1:]] = 1
        self._uploaded_size += uploaded_size
        nb_f: str = ", ".join([f"{k}: {v}" for k, v in self._nb_files.items()])
        total = sum(list(self._nb_files.values()))

        files_to_upload = ", ".join(
            [
                f"{filetype}: {nb}"
                for filetype, nb in list_nb_files(local_dir).items()
            ]
        )

        latest_uploaded = str(files[0].stem) if files else ""

        self._status.entries(
            FtpRunnerEntries(
                number_uploaded_files=f"{total} ({nb_f})",
                total_uploaded_files=bits_to_human(self._uploaded_size),
                upload_speed=self._upload_speed.get(),
                files_to_upload=files_to_upload,
                latest_uploaded=latest_uploaded,
            )
        )

    def _upload_files(
        self,
        ftp_config: FtpConfig,
        remote_dir: Path,
        files: List[Path],
    ) -> int:
        """
        Upload the files to the remote directory and returns
        the total size uploaded
        """
        self._status.activity("connecting to ftp server")

        # we create a new connection at each iteration.
        # this proved to be more stable.
        with get_ftp(ftp_config, remote_dir) as ftp:
            delete_local = True
            self._status.activity("uploading files")
            uploaded_size = ftp.upload(files, delete_local)
        return uploaded_size

    def iterate(self):
        """
        Upload images and metadata to remote server
        """

        # reading the toml config file
        config = self.get_config()

        # where the files to upload are
        local_dir = Path(config["source_folder"])
        local_dir.mkdir(exist_ok=True, parents=True)

        # listing the files to upload located in local_dir, ordered newest first.
        dated_files = sort_by_night(local_dir)

        if dated_files:
            # there are files to upload

            # creating the ftp connection config based
            # on the runner config
            ftp_config = _get_ftp_config(config)
            remote_subdir = str(config["remote_subdir"])

            # maximum number of files that can be uploaded
            # per connection.
            batch = int(config["batch"])

            # selecting the files to upload
            date_files = dated_files[0]
            date = date_files[0]
            files_ = date_files[1]
            files = [f[1] for f in files_][:batch]

            if files:
                self.log(
                    Level.info,
                    f"uploading {', '.join([f.stem for f in files])}",
                )
                # the remote folder name will be :
                # the name of the system / the current date
                remote_dir = _get_remote_dir(
                    remote_subdir, date, str(config["nightskycam"])
                )

                # uploading data
                uploaded_size = self._upload_files(
                    ftp_config, remote_dir, files
                )
                self._upload_speed.add(uploaded_size)
                self._update_status(files, uploaded_size, local_dir)
            else:
                self._update_status([], 0, local_dir)
        else:
            self._update_status([], 0, local_dir)
