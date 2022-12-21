import os
import typing
import logging
from ftplib import FTP
from socket import gaierror
from pathlib import Path
import threading

from pyftpdlib.authorizers import DummyAuthorizer
from pyftpdlib.handlers import FTPHandler
from pyftpdlib.servers import ThreadedFTPServer

Files = typing.Union[Path, typing.Iterable[Path]]
_logger = logging.getLogger("ftp")


class FtpConfig:
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


class FtpServer:
    def __init__(self, config: FtpConfig):

        if config.folder is None:
            config.folder = Path(os.getcwd())

        authorizer = DummyAuthorizer()
        authorizer.add_user(
            config.username, config.passwd, str(config.folder), perm="elradfmwMT"
        )
        handler = FTPHandler
        handler.authorizer = authorizer
        self._server = ThreadedFTPServer((config.host, config.port), handler)
        self._thread: typing.Optional[threading.Thread] = None

    def start(self):
        self._thread = threading.Thread(target=self._server.serve_forever)
        self._thread.deamon = True
        self._thread.start()

    def stop(self):
        if self._thread is not None:
            self._server.close_all()
            self._thread.join()
            self._thread = None


class FTPError(Exception):
    pass


class FTPWarning(Exception):
    pass


def connect(
    host: str,
    port: typing.Optional[int] = None,
    username: typing.Optional[str] = None,
    passwd: typing.Optional[str] = None,
) -> FTP:

    ftp = FTP()

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


def cd(ftp: FTP, remote_path: Path) -> None:
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


def rmdir(ftp: FTP, folder: str) -> None:
    cd(ftp, Path(folder))
    content = ftp.nlst()
    for c in content:
        try:
            ftp.delete(c)
        except Exception:
            rmdir(ftp, f"{folder}/{c}")
    parts = Path(folder).parts
    cd(ftp, Path(*parts[:-1]))
    ftp.rmd(parts[-1])


class Ftp:
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

        self.ftp: FTP = connect(
            self.host, port=self.port, username=self.username, passwd=self.passwd
        )
        _logger.debug(f"connected to {self.host}")
        if remote_path is not None:
            _logger.debug(f"cd to {remote_path}")
            try:
                cd(self.ftp, remote_path)
            except Exception as e:
                self.ftp.close()
                raise e

    def delete(self) -> None:
        if self.remote_path is not None:
            rmdir(self.ftp, str(self.remote_path))
        self.close()

    def ls(self) -> typing.List[str]:
        return self.ftp.nlst()

    def cd(self, subfolder: str) -> None:
        cd(self.ftp, Path(subfolder))

    def _upload(self, path: Path, delete_local: bool) -> int:

        if not path.is_file():
            raise FileNotFoundError(f"FTP upload: failed to find " f"local file {path}")

        local_file_size: int = path.stat().st_size
        filename: str = path.name

        if filename in self.ftp.nlst():
            self.ftp.delete(filename)
        try:
            with open(path, "rb") as f:
                self.ftp.storbinary(f"STOR {filename}", f)
        except Exception as e:
            raise FTPError(f"Failed to upload {path}: {e}")

        remote_file_size: typing.Optional[int] = self.ftp.size(filename)

        self.nb_uploaded_files += 1
        self.upload_size += local_file_size

        if remote_file_size is not None:
            if local_file_size != remote_file_size:
                raise FTPWarning(
                    f"{path}: size of the local file is {local_file_size} "
                    f"while size of uploaded file is {remote_file_size}"
                )
        _logger.debug(f"uploaded {filename} ({remote_file_size} bytes)")

        if delete_local:
            path.unlink()
            _logger.debug(f"deleted {filename}")

        return local_file_size

    def upload(self, files: Files, delete_local: bool) -> int:

        total_size = 0

        warnings = []

        if isinstance(files, Path):
            files = [files]

        for index, f in enumerate(files):

            try:
                total_size += self._upload(f, delete_local)
            except FTPWarning as warning:
                warnings.append(warning)
            except FTPError as error:
                raise error

        if warnings:
            raise FTPWarning("\n".join([str(w) for w in warnings]))

        return total_size

    def upload_dir(
        self,
        local_path: Path,
        extensions: typing.Sequence[str] = None,
        delete_local: bool = False,
        batch_size: typing.Optional[int] = None,
        glob: typing.Optional[str] = None,
    ) -> typing.Tuple[int, int]:

        if not local_path.is_dir():
            raise FileNotFoundError(
                f"Failed to upload the content of {local_path}: " "folder not found"
            )

        files: typing.List[Path] = []
        uploaded_size = 0

        if extensions is not None:
            for extension in extensions:
                files.extend(local_path.glob("*." + extension))
        else:
            if glob is None:
                files = list(filter(lambda x: x.is_file(), local_path.glob("*")))
            else:
                files = list(filter(lambda x: x.is_file(), local_path.glob(glob)))

        if batch_size and len(files) > batch_size:
            files = files[:batch_size]

        if files:
            _logger.info(f"uploading {len(files)} file(s) to {self.host}")
            uploaded_size = self.upload(files, delete_local)
            _logger.info(f"uploaded {uploaded_size} bytes")

        return len(files), uploaded_size

    def close(self):
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
        return (self.nb_uploaded_files, self.upload_size)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        self.close()


class get_ftp:
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
