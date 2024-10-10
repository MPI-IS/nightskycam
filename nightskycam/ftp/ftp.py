"""
Module defining FTP servers and clients. 
Used by [nightskycam.ftp.runner.FtpRunner]() and
related unit-tests.
"""

from typing import Tuple
from typing import Optional
from typing_extensions import TypeAlias
from typing import Union
import logging
import os
import threading
import typing
from ftplib import FTP, FTP_TLS
from pathlib import Path
from socket import gaierror

from pyftpdlib.authorizers import DummyAuthorizer
from pyftpdlib.handlers import FTPHandler
from pyftpdlib.servers import ThreadedFTPServer

Files = typing.Union[Path, typing.Iterable[Path]]
_logger = logging.getLogger("ftp")


class FtpConfig:
    """
    Configuration of a FTP server.
    """

    def __init__(
        self,
        username: str,
        passwd: str,
        host: str = "127.0.0.1",
        port: int = 2121,
        folder: typing.Optional[Path] = None,
    ):
        self.username = username
        self.passwd = passwd
        self.folder = folder
        self.host = host
        self.port = port

    def __str__(self) -> str:
        s = ", ".join(
            [
                f"{attr}: {getattr(self,attr)}"
                for attr in ("username", "passwd", "folder", "host", "port")
            ]
        )
        return f"FtpConfig: {s}"


class FtpServer:
    """
    Spawn a local FTP server based on the configuration passed as
    argument.
    Not secured, for testing purposes only.
    """

    def __init__(self, config: FtpConfig):
        if config.folder is None:
            config.folder = Path(os.getcwd())

        authorizer = DummyAuthorizer()
        authorizer.add_user(
            config.username,
            config.passwd,
            str(config.folder),
            perm="elradfmwMT",
        )
        handler = FTPHandler
        handler.authorizer = authorizer
        self._server = ThreadedFTPServer((config.host, config.port), handler)
        self._thread: typing.Optional[threading.Thread] = None

    def start(self):
        """
        Starts the server.
        """
        self._thread = threading.Thread(target=self._server.serve_forever)
        self._thread.start()

    def stop(self):
        """
        Stops the server.
        """
        if self._thread is not None:
            self._server.close_all()
            self._server.serve_forever(timeout=0)
            self._thread.join()
            self._thread = None


class FTPError(Exception):
    pass


class FTPWarning(Exception):
    pass


class _FTP_TLS(FTP_TLS):
    # See: https://stackoverflow.com/questions/14659154/ftps-with-python-ftplib-session-reuse-required
    def ntransfercmd(self, cmd, rest=None):
        conn, size = FTP.ntransfercmd(self, cmd, rest)
        if self._prot_p:
            conn = self.context.wrap_socket(
                conn, server_hostname=self.host, session=self.sock.session
            )
        return conn, size


Ftp: TypeAlias = Union[FTP, _FTP_TLS]


def _simpler_connect(
    host: str,
    port: typing.Optional[int] = None,
    username: typing.Optional[str] = None,
    passwd: typing.Optional[str] = None,
    timeout: typing.Optional[float] = 10,
) -> FTP:
    # connects to the ftp server.
    # Used internally by Ftp (see below)

    if timeout is None:
        ftp = FTP()
    else:
        ftp = FTP(timeout=timeout)

    try:
        if port is None:
            ftp.connect(host)
        else:
            ftp.connect(host, port)
    except gaierror as ge:
        host_str = host
        if port:
            host_str += f":{port}"
        raise FTPError(f"failed to connect to {host_str}: {ge}")

    if username is not None and passwd is not None:
        try:
            ftp.login(username, passwd)
        except Exception as e:
            raise FTPError(f"failed to login to {host}: {e}")
    else:
        try:
            ftp.login()
        except Exception as e:
            raise FTPError(f"failed to login to {host}: {e}")

    return ftp


def _connect(
    host: str,
    port: typing.Optional[int] = None,
    username: typing.Optional[str] = None,
    passwd: typing.Optional[str] = None,
    timeout: typing.Optional[float] = 10,
) -> Ftp:
    tls: bool
    if username is None or passwd is None:
        ftp_class = FTP
        tls = False
    else:
        ftp_class = _FTP_TLS
        tls = True
    ftp_instance = ftp_class(timeout=timeout)
    try:
        ftp_instance.connect(host, port=port)
        if tls:
            ftp_instance.login(user=username, passwd=passwd)
            ftp_instance.prot_p()
        else:
            ftp_instance.login()
    except Exception as e:
        try:
            return _simpler_connect(host, port, username, passwd, timeout)
        except FTPError:
            host_str = f"{host}:{port}"
            if tls:
                host_str = f"{host_str} (TLS)"
            raise FTPError(f"failed to login to {host_str}: {e}")
    return ftp_instance


def _cd(ftp: Ftp, remote_path: Path) -> None:
    # change the current remote ftp directory,
    # used internally by Ftp (see below)

    ftp.cwd("/")
    parts = remote_path.parts
    try:
        for subfolder in parts:
            if subfolder != "/":
                if subfolder not in ftp.nlst():
                    ftp.mkd(subfolder)
            ftp.cwd(subfolder)
    except Exception as e:
        raise FTPError(f"Failed to create/cd directory {remote_path}: " f"{e}")


def _rmdir(ftp: Ftp, folder: str) -> None:
    # delete the remote directory,
    # used internally by Ftp (see below)

    _cd(ftp, Path(folder))
    content = ftp.nlst()
    for c in content:
        try:
            ftp.delete(c)
        except Exception:
            _rmdir(ftp, f"{folder}/{c}")
    parts = Path(folder).parts
    _cd(ftp, Path(*parts[:-1]))
    ftp.rmd(parts[-1])


class Ftp:
    """
    Utility class for connecting to a FTP server and using this connection.
    Files will be uploaded to the remote folder "remote_path" (which will be
    created if it does not exists).
    """

    def __init__(
        self,
        config: FtpConfig,
        remote_path: typing.Optional[Path] = None,
    ):
        self.host = config.host
        self.remote_path = remote_path
        self.username = config.username
        self.passwd = config.passwd
        self.port = config.port
        self.upload_size: int = 0
        self.nb_uploaded_files: int = 0

        self.ftp: Ftp = _connect(
            self.host,
            port=self.port,
            username=self.username,
            passwd=self.passwd,
        )
        _logger.debug(f"connected to {self.host}")
        if remote_path is not None:
            _logger.debug(f"cd to {remote_path}")
            try:
                _cd(self.ftp, remote_path)
            except Exception as e:
                self.ftp.close()
                raise e

    def delete(self) -> None:
        """
        Delete "remote_path" (see constructor)
        """
        if self.remote_path is not None:
            _rmdir(self.ftp, str(self.remote_path))
        self.close()

    def ls(self) -> typing.List[str]:
        """
        List the content of the current remote folder
        """
        return self.ftp.nlst()

    def cd(self, subfolder: str) -> None:
        """
        Change the current remote folder
        """
        _cd(self.ftp, Path(subfolder))

    def _upload(self, path: Path, delete_local: bool) -> int:
        # upload the file at "path".

        # file to upload not found
        if not path.is_file():
            raise FileNotFoundError(
                f"FTP upload: failed to find " f"local file {path}"
            )

        # getting the size of the file, will be used to check
        # the file has been properly uploaded.
        local_file_size: int = path.stat().st_size

        # deleting the remote file of the same name, if any
        filename: str = path.name
        if filename in self.ftp.nlst():
            self.ftp.delete(filename)

        # uploading the file
        try:
            with open(path, "rb") as f:
                self.ftp.storbinary(f"STOR {filename}", f)
        except Exception as e:
            raise FTPError(f"Failed to upload {path}: {e}")

        # checking the size of the remote uploaded file
        remote_file_size: typing.Optional[int] = self.ftp.size(filename)

        # keeping track of the number of files this FTP connection
        # has uploaded
        self.nb_uploaded_files += 1
        self.upload_size += local_file_size

        # the upload did not work as expected: the size of the remote
        # file is not the same as the size of the local file.
        # exiting with error.
        if remote_file_size is not None:
            if local_file_size != remote_file_size:
                raise FTPWarning(
                    f"{path}: size of the local file is {local_file_size} "
                    f"while size of uploaded file is {remote_file_size}"
                )
        _logger.debug(f"uploaded {filename} ({remote_file_size} bytes)")

        # no error, deleting local file.
        if delete_local:
            path.unlink()
            _logger.debug(f"deleted {filename}")

        # returning the size of the uploaded data.
        return local_file_size

    def upload(self, files: Files, delete_local: bool) -> int:
        """
        Upload the local files to the current remote directory.
        If delete_local is True, local files are deleted after
        successful upload.
        The total uploaded size is returned.
        """
        total_size = 0

        warnings = []

        if isinstance(files, Path):
            files = [files]

        for f in files:
            try:
                total_size += self._upload(f, delete_local)
            except FTPWarning as warning:
                warnings.append(warning)
            except FTPError as error:
                raise error

        if warnings:
            # at least one file was not properly uploaded.
            raise FTPWarning("\n".join([str(w) for w in warnings]))

        return total_size

    def upload_dir(
        self,
        local_path: Path,
        extensions: typing.Optional[typing.Sequence[str]] = None,
        delete_local: bool = False,
        batch_size: typing.Optional[int] = None,
        glob: typing.Optional[str] = None,
    ) -> typing.Tuple[int, int]:
        """
        Upload all the files contained in "local_path".
        If "extensions" is not None, only the files of the specified extensions
        will be uploaded.
        If "delete_local" is True, local files which have been successfully uploaded
        will be deleted.
        If "batch_size" is not None, at most "batch_size" files will be uploaded.
        If "extensions" is None and "glob" is not None, "glob" will be used
        to select the files that can be uploaded.
        """
        if not local_path.is_dir():
            raise FileNotFoundError(
                f"Failed to upload the content of {local_path}: "
                "folder not found"
            )

        files: typing.List[Path] = []
        uploaded_size = 0

        if extensions is not None:
            for extension in extensions:
                files.extend(local_path.glob("*." + extension))
        else:
            if glob is None:
                files = list(
                    filter(lambda x: x.is_file(), local_path.glob("*"))
                )
            else:
                files = list(
                    filter(lambda x: x.is_file(), local_path.glob(glob))
                )

        if batch_size and len(files) > batch_size:
            files = files[:batch_size]

        if files:
            _logger.info(f"uploading {len(files)} file(s) to {self.host}")
            uploaded_size = self.upload(files, delete_local)
            _logger.info(f"uploaded {uploaded_size} bytes")

        return len(files), uploaded_size

    def close(self):
        """
        Close the FTP connection.
        """
        try:
            self.ftp.quit()
        except Exception:
            pass
        try:
            self.ftp.close()
        except Exception:
            pass
        _logger.debug(f"closed connection to {self.host}")

    def get_stats(self) -> typing.Tuple[int, int]:
        """
        Returns the tuple:
        - number of uploaded files by this connection
        - total uploaded data size of this connection
        """
        return (self.nb_uploaded_files, self.upload_size)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        self.close()


class get_ftp:
    """
    Context manager for [Ftp]() (making sure the connection
    is properly closed).
    """

    def __init__(
        self,
        config: FtpConfig,
        remote_dir: Path,
    ) -> None:
        self.ftp = Ftp(config, remote_dir)

    def __enter__(self):
        return self.ftp

    def __exit__(self, exception_type, exception_value, exception_traceback):
        self.ftp.close()
