import threading
import time
import subprocess
import typing
import logging
from pathlib import Path
from .utils.remote_download import list_remote_files, download_file


_logger = logging.getLogger("command")

_nightskycam_command_folder = Path("/opt/nightskycam/command")
_nightskycam_previous_command_file = _nightskycam_command_folder / "previous.txt"


def command_folder() -> Path:
    global _nightskycam_command_folder
    if not _nightskycam_command_folder.is_dir():
        try:
            _nightskycam_command_folder.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            raise RuntimeError(
                f"nightskycam command folder ({_nightskycam_command_folder}) "
                f"could not be create: {e}"
            )
    return _nightskycam_command_folder


def previous_command() -> typing.Optional[str]:
    if not _nightskycam_previous_command_file.is_file():
        return None
    return _nightskycam_previous_command_file.read_text()


def get_remote_command_file(
    url: str, timeout: typing.Optional[float] = 10.0
) -> typing.Optional[str]:
    def _is_valid(filename: str) -> bool:
        return filename.startswith("command_") and filename.endswith(".txt")

    filenames = list_remote_files(url, timeout, _is_valid)
    if not filenames:
        return None
    if len(filenames) > 1:
        raise ValueError(
            f"found more than one command file ('command_*.txt') at remote {url}"
        )
    return filenames[0]


def new_command_file(
    url: str, timeout: typing.Optional[float] = 10.0
) -> typing.Optional[str]:

    filename = get_remote_command_file(url, timeout)
    previous = previous_command()
    if previous is None:
        return filename
    if filename != previous:
        return filename
    return None


def download_new_command(
    url: str, timeout: typing.Optional[float] = 10.0
) -> typing.Optional[Path]:

    filename = new_command_file(url, timeout)
    if filename is None:
        return None
    folder = command_folder()
    download_file(url, filename, folder)
    downloaded_file = folder / filename
    return downloaded_file


class CommandResult:
    def __init__(
        self,
    ):
        self.filename: str = ""
        self.return_code: int = -1
        self.stdout: str = ""
        self.stderr: str = ""


def execute_new_command(
    url: str, timeout: typing.Optional[float] = 10.0
) -> typing.Optional[CommandResult]:

    filepath = download_new_command(url, timeout)

    if filepath is None:
        return None

    output = subprocess.run(["/bin/bash", f"{filepath}"], capture_output=True)

    with open(_nightskycam_previous_command_file, "w") as f:
        f.write(filepath.name)

    result = CommandResult()
    result.filename = filepath.name
    result.return_code = output.returncode
    result.stdout = output.stdout.decode("utf-8")
    result.stderr = output.stderr.decode("utf-8")

    filepath.unlink()

    return result


class CommandRun:
    def __init__(self, filepath: Path) -> None:
        self._filepath = filepath
        self._content: str = self._filepath.read_text()
        self._result: typing.Optional[CommandResult] = None
        self._time_start = time.time()
        self._thread: typing.Optional[threading.Thread] = None
        self._lock = threading.Lock()
        with self._lock:
            self.run()

    def run(self):
        self._thread = threading.Thread(target=self._run_command)
        self._thread.start()

    def _run_command(self):

        output = subprocess.run(["/bin/bash", f"{self._filepath}"], capture_output=True)

        with open(_nightskycam_previous_command_file, "w") as f:
            f.write(self._filepath.name)

        self._result = CommandResult()
        self._result.filename = self._filepath.name
        self._result.return_code = output.returncode
        self._result.stdout = output.stdout.decode("utf-8")
        self._result.stderr = output.stderr.decode("utf-8")

        self._filepath.unlink()

    def status(self) -> typing.Optional[str]:
        with self._lock:
            if self._thread is not None and not self._thread.is_alive():
                self._thread = None
            if self._thread is None:
                return None
        duration = time.time() - self._time_start
        return f"running for {duration:.2f} seconds\n{self._content}"

    def result(self) -> typing.Optional[CommandResult]:
        return self._result
