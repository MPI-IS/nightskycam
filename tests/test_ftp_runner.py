import tempfile
import time
import typing
from datetime import datetime, timedelta
from pathlib import Path
from typing import Generator, List

import pytest
from nightskycam.ftp.runner import FtpRunner, _UploadSpeed
from nightskycam.utils.filename import get_filename
from nightskycam.utils.ftp import FtpConfig, FtpServer, get_ftp
from nightskycam.utils.test_utils import (
    ConfigTester,
    configuration_test,
    had_error,
    get_manager,
    runner_started,
    wait_for,
)
from nightskyrunner.config import Config
from nightskyrunner.shared_memory import SharedMemory


@pytest.fixture
def reset_memory(
    request,
    scope="function",
) -> Generator[None, None, None]:
    """
    Fixture clearing the nightskyrunner shared memory
    upon exit.
    """
    try:
        yield None
    finally:
        SharedMemory.clear()


@pytest.fixture
def tmp_dir(request, scope="function") -> Generator[Path, None, None]:
    """
    Fixture yielding a temp directory.
    """
    folder_ = tempfile.TemporaryDirectory()
    folder = Path(folder_.name)
    try:
        yield folder
    finally:
        folder_.cleanup()


@pytest.fixture
def ftp_server(request, scope="function") -> Generator[FtpConfig, None, None]:
    """
    starts a ftp server running over a tmp directory
    """
    username = "utest"
    passwd = "utestpwd"
    server_dir_ = tempfile.TemporaryDirectory()
    server_dir = Path(server_dir_.name)
    config = FtpConfig(username, passwd, folder=server_dir)
    server = FtpServer(config)
    server.start()
    yield config
    server.stop()
    server_dir_.cleanup()


def test_stop_ftp_server(tmp_dir) -> None:
    """
    Test the ftp server properly exits
    (i.e. no "address already in use" when stopping
    a server and starting a new one).
    """
    username = "utest"
    passwd = "utestpwd"
    server_dir_ = tempfile.TemporaryDirectory()
    server_dir = Path(server_dir_.name)
    config = FtpConfig(username, passwd, folder=server_dir)

    for _ in range(3):
        server = FtpServer(config)
        server.start()
        time.sleep(0.5)
        server.stop()


def test_ftp_delete(ftp_server) -> None:
    """
    Test the method nightskycam.ftp.Ftp.delete
    """
    config: FtpConfig = ftp_server

    # the only subfolder our ftp client
    # should be allowed to delete !
    remote_subdir = Path("remote/sub/dir")

    # creating some content at the root of
    # the ftp server. This data represents
    # the data that have been uploaded by other user
    # and process and should ABSOLUTELY NOT get deleted !
    if config.folder is None:
        raise ValueError("for this test, the c")
    server_root = Path(config.folder)
    f1 = server_root / "f1.txt"
    with open(f1, "w+") as f:
        f.write("important content")
    subdir = server_root / "subdir"
    subdir.mkdir(parents=False, exist_ok=True)
    f2 = subdir / "f2.txt"
    with open(f2, "w+") as f:
        f.write("important content")

    with get_ftp(config, remote_subdir) as ftp:
        # creating content in remote_subdir
        abs_remote_subdir = ftp_server.folder / remote_subdir
        d1 = abs_remote_subdir / "d1.txt"
        with open(d1, "w+") as f:
            f.write("trivial content")
        trivial_subdir = abs_remote_subdir / "subdir"
        trivial_subdir.mkdir(parents=False, exist_ok=True)
        d2 = trivial_subdir / "d2.txt"
        with open(d2, "w+") as f:
            f.write("trivial content")

        # deleting remote_subdir
        ftp.delete()

    # checking remote_subdir no longer exists
    assert not abs_remote_subdir.is_dir()

    # checking the rest still exists
    assert config.folder.is_dir()
    assert subdir.is_dir()
    assert f1.is_file()
    assert f2.is_file()


def test_ftp(ftp_server) -> None:
    """
    Test the class nightskycam.ftp.Ftp
    """

    config: FtpConfig = ftp_server

    if not config.folder:
        raise ValueError(
            "the configuration folder needs to be set for this test"
        )

    # the files will be copied in this subfolders
    # of the ftp server
    remote_subdir = Path("remote/sub/dir")

    nb_files = 3

    def _get_file(
        client_dir: Path, index: int, filename_prefix: str
    ) -> typing.Tuple[str, str]:
        filename = f"{filename_prefix}_{index}"
        path = client_dir / f"{filename_prefix}_{index}"
        content = f"content of test file {index}"
        with open(path, "w+") as f:
            f.write(content)
        return filename, content

    with tempfile.TemporaryDirectory() as client_content_dir_:
        client_content_dir = Path(client_content_dir_)

        # creating some files in a tmp folder
        files: typing.List[typing.Tuple[str, str]] = [
            _get_file(client_content_dir, index, "test_file")
            for index in range(nb_files)
        ]

        # uploading the files
        with get_ftp(config, remote_subdir) as ftp:
            # uploading the files, not deleting the originals
            ftp.upload_dir(client_content_dir, delete_local=False)

            # checking the right number of file
            # have been uploaded
            nb_uploaded_files, upload_size = ftp.get_stats()
            assert nb_uploaded_files == nb_files

            # checking the files have been uploaded
            for filename, content in files:
                remote_path = config.folder / remote_subdir / filename
                assert remote_path.is_file()
                with open(remote_path, "r") as fr:
                    read_content = fr.read()
                    assert (read_content) == content

            # checking the files have been uploaded,
            # this time using the Ftp API
            ftp.cd(remote_subdir)
            remote_files = ftp.ls()
            assert len(remote_files) == nb_files
            for filename, _ in files:
                assert filename in remote_files

            # deleting the remote directory in which
            # files have been uploaded
            ftp.delete()
            assert not (config.folder / remote_subdir).is_dir()

        # uploading the files once more, this time deleting
        # the original files
        with get_ftp(config, remote_subdir) as ftp:
            # uploading the files, not deleting the originals
            ftp.upload_dir(client_content_dir, delete_local=True)

            # checking the right number of file
            # have been uploaded
            nb_uploaded_files, upload_size = ftp.get_stats()
            assert nb_uploaded_files == nb_files

            # checking the files have been uploaded
            for filename, content in files:
                remote_path = config.folder / remote_subdir / filename
                assert remote_path.is_file()
                with open(remote_path, "r") as fr:
                    read_content = fr.read()
                    assert (read_content) == content

            # checking the original files have been deleted
            for filename, _ in files:
                assert not (client_content_dir / filename).is_file()


def test_upload_speed_empty() -> None:
    """
    Test the class ftp.runner._UploadSpeed
    """
    memory_in_sec = 5.0
    us = _UploadSpeed(memory_in_sec=memory_in_sec)
    assert us.get() == 0.0
    us.add(1.0, 1.0)
    assert us.get(now=1.1) == 0.0
    us.add(1.0, 2.0)
    assert us.get(now=2.1) == 2.0
    assert us.get(now=memory_in_sec + 3) == 0


class _FtpRunnerConfig:
    @classmethod
    def get_config(
        cls,
        system_name: str,
        remote_subdir: str,
        folder: Path,
        unsupported: bool = False,
    ) -> Config:
        if unsupported:
            return {
                "source_folder": "/not/a/valid/path",
                "batch": "not an int",
                "username": "nottheusername",
                "host": "125.13.1.48",
                "port": 2001,
            }
        else:
            return {
                "frequency": 5.0,
                "source_folder": str(folder),
                "remote_subdir": remote_subdir,
                "batch": 3,
                "username": "utest",
                "password": "utestpwd",
                "host": "127.0.0.1",
                "port": 2121,
                "nightskycam": system_name,
            }

    @classmethod
    def get_config_tester(
        cls, system_name: str, remote_subdir: str, folder: Path
    ) -> ConfigTester:
        return ConfigTester(
            cls.get_config(
                system_name, remote_subdir, folder, unsupported=False
            ),
            cls.get_config(
                system_name, remote_subdir, folder, unsupported=True
            ),
        )


def _write_ordered_date_formated_files(
    target_folder: Path,
    start_date: str,
    nb_files: int,
    system_name: str = "test_system",
) -> List[Path]:
    r: List[Path] = []
    start_date_ = datetime.strptime(start_date, "%Y_%m_%d_%H_%M_%S")
    for i in range(nb_files):
        next_date = start_date_ + timedelta(minutes=5 * i)
        filename = get_filename(system_name, next_date)
        path = target_folder / f"{filename}.test"
        with open(path, "w") as f:
            f.write(" ")
        r.append(path)
    return r


def _list_files(target_folder) -> List[Path]:
    r: List[Path] = []
    for item in target_folder.iterdir():
        if item.is_file():
            r.append(item.absolute())
    return r


def test_configuration(tmp_dir, ftp_server, reset_memory):
    """
    Testing instances of FtpRunner behave correctly
    to changes of configuration.
    """
    _write_ordered_date_formated_files(tmp_dir, "2023_01_01_01_01_01", 100)
    config_tester = _FtpRunnerConfig.get_config_tester(
        "test_system", "test", str(tmp_dir)
    )
    configuration_test(FtpRunner, config_tester, timeout=30.0)


def test_ftp_runner(tmp_dir, ftp_server, reset_memory) -> None:
    """
    Testing instances of FtpRunner behave as expected
    """

    def _nb_files_decreased(
        tmp_dir: Path, nb_files: int, nb_uploaded: int
    ) -> bool:
        return len(_list_files(tmp_dir)) <= nb_files - nb_uploaded

    ftp_config: FtpConfig = ftp_server
    system_name = "test_system"
    remote_subdir = "test"
    config: Config = _FtpRunnerConfig.get_config(
        system_name, remote_subdir, tmp_dir
    )
    nb_files = 50
    nb_uploaded = 6
    day = "2023_01_01"
    start_date = f"{day}_14_30_00"
    files_to_upload: List[Path]

    with get_manager((FtpRunner, config)):
        # checking runner does not raise exception upon no files to upload
        wait_for(runner_started, True, args=(FtpRunner.__name__,))
        assert not had_error(FtpRunner.__name__)

        # adding files to upload
        files_to_upload = _write_ordered_date_formated_files(
            tmp_dir, start_date, nb_files
        )

        # waiting for at least nb_uploaded files to be uploaded
        wait_for(
            _nb_files_decreased, True, args=(tmp_dir, nb_files, nb_uploaded)
        )
        assert not had_error(FtpRunner.__name__)

    # checking files have been uploaded
    target_dir = ftp_config.folder / remote_subdir / system_name / day  # type: ignore

    remote_files = _list_files(target_dir)
    assert len(remote_files) >= nb_uploaded
    assert len(_list_files(tmp_dir)) == nb_files - len(remote_files)
    assert set([rf.stem for rf in remote_files]) == set(
        [fu.stem for fu in files_to_upload[-len(remote_files) :]]
    )
