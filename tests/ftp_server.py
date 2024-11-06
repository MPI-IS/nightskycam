"""
Module for testing [nightskycam.ftp.ftp]().
"""

import tempfile
import typing
from pathlib import Path

import pytest
from nightskycam.utils.ftp import FtpConfig, FtpServer, get_ftp


@pytest.fixture
def ftp_server(request, scope="function") -> typing.Generator[FtpConfig, None, None]:
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
    server_root = Path(str(config.folder))
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
    if config.folder is not None:
        assert config.folder.is_dir()
    assert subdir.is_dir()
    assert f1.is_file()
    assert f2.is_file()


def test_ftp(ftp_server) -> None:
    """
    Test the class nightskycam.ftp.Ftp
    """

    config: FtpConfig = ftp_server

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
            if config.folder is None:
                # for mypy's sake
                raise ValueError()

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
