import typing
import tempfile
from pathlib import Path
import nightskycam

from ftp_server import ftp_server  # noqa: F401


def test_ftp_delete(ftp_server):  # noqa: F811
    """
    Test the method nightskycam.ftp.Ftp.delete
    """
    config: nightskycam.FtpConfig = ftp_server

    # the only subfolder our ftp client
    # should be allowed to delete !
    remote_subdir = Path("remote/sub/dir")

    # creating some content at the root of
    # the ftp server. This data represents
    # the data that have been uploaded by other user
    # and process and should ABSOLUTELY NOT get deleted !
    server_root = Path(config.folder)
    f1 = server_root / "f1.txt"
    with open(f1, "w+") as f:
        f.write("important content")
    subdir = server_root / "subdir"
    subdir.mkdir(parents=False, exist_ok=True)
    f2 = subdir / "f2.txt"
    with open(f2, "w+") as f:
        f.write("important content")

    with nightskycam.utils.ftp.get_ftp(config, remote_subdir) as ftp:

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


def test_ftp(ftp_server):  # noqa: F811
    """
    Test the class nightskycam.ftp.Ftp
    """

    config: nightskycam.utils.ftp.FtpConfig = ftp_server

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
        with nightskycam.utils.ftp.get_ftp(config, remote_subdir) as ftp:

            # uploading the files, not deleting the originals
            ftp.upload_dir(client_content_dir, delete_local=False)

            # checking the right number of file
            # have been uploaded
            nb_uploaded_files, upload_size = ftp.get_stats()
            assert nb_uploaded_files == nb_files

            # checking the files have been uploaded
            for (filename, content) in files:
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
            for (filename, _) in files:
                assert filename in remote_files

            # deleting the remote directory in which
            # files have been uploaded
            ftp.delete()
            assert not (config.folder / remote_subdir).is_dir()

        # uploading the files once more, this time deleting
        # the original files
        with nightskycam.utils.ftp.get_ftp(config, remote_subdir) as ftp:

            # uploading the files, not deleting the originals
            ftp.upload_dir(client_content_dir, delete_local=True)

            # checking the right number of file
            # have been uploaded
            nb_uploaded_files, upload_size = ftp.get_stats()
            assert nb_uploaded_files == nb_files

            # checking the files have been uploaded
            for (filename, content) in files:
                remote_path = config.folder / remote_subdir / filename
                assert remote_path.is_file()
                with open(remote_path, "r") as fr:
                    read_content = fr.read()
                    assert (read_content) == content

            # checking the original files have been deleted
            for (filename, _) in files:
                assert not (client_content_dir / filename).is_file()


def test_success_ftp_skythread(ftp_server):  # noqa: F811

    # configuration of the ftp server
    server_config: nightskycam.utils.ftp.FtpConfig = ftp_server

    # where the files will be copied by FTP
    remote_folder = (
        server_config.folder / nightskycam.skythreads.ftp_thread.get_remote_dir()
    )

    # client side folder (location of files to upload)
    with tempfile.TemporaryDirectory() as client_content_dir_:

        client_content_dir = Path(client_content_dir_)

        main_config: nightskycam.types.Configuration = {}

        # configuration of the FtpThread instance
        ftp_config: nightskycam.types.Configuration = {
            "port": server_config.port,
            "host": server_config.host,
            "username": server_config.username,
            "passwd": server_config.passwd,
            "local_dir": client_content_dir,
            "upload_every": 1,
            "batch": 10,
        }

        # creating the configuration getter that will
        # return this config
        thread_config: nightskycam.types.GlobalConfiguration = {
            "main": main_config,
            "FtpThread": ftp_config,
        }
        config_getter = nightskycam.configuration_getter.DictConfigurationGetter(
            thread_config
        )

        # checking the config is ok
        output = nightskycam.skythreads.FtpThread.check_config(config_getter)
        assert output is None

        # instantiating FtpThread and running the deploy test
        ftp_thread = nightskycam.skythreads.FtpThread(config_getter)
        output = ftp_thread.deploy_test()
        assert output is None

        # running the execute function. As the client content directory
        # is empty, we expect nothing to occur
        nb_remote_files = len(
            list(remote_folder.glob("*"))
        )  # files uploaded during deploy
        ftp_thread._execute()
        assert len(list(remote_folder.glob("*"))) == nb_remote_files

        # creating files in the client content directory
        f1 = client_content_dir / "f1.txt"
        f2 = client_content_dir / "f2.txt"
        for path in (f1, f2):
            with open(path, "w+") as f:
                f.write("test content")

        # running execute again, f1 and f2 should be uploaded
        # to the remote, and deleted locally
        ftp_thread._execute()
        assert len(list(remote_folder.glob("*"))) == nb_remote_files + 2
        assert (remote_folder / "f1.txt").is_file()
        assert (remote_folder / "f2.txt").is_file()
        assert not f1.is_file()
        assert not f2.is_file()
