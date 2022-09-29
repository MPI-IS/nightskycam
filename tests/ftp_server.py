from pathlib import Path
import typing
import pytest
import nightskycam
import tempfile


@pytest.fixture
def ftp_server(
    request, scope="function"
) -> typing.Generator[nightskycam.utils.ftp.FtpConfig, None, None]:
    """
    starts a ftp server running over a tmp directory
    """
    username = "utest"
    passwd = "utestpwd"
    server_dir_ = tempfile.TemporaryDirectory()
    server_dir = Path(server_dir_.name)
    config = nightskycam.utils.ftp.FtpConfig(username, passwd, folder=server_dir)
    server = nightskycam.utils.ftp.FtpServer(config)
    server.start()
    yield config
    server.stop()
    server_dir_.cleanup()
