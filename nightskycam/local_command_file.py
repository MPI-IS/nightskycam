import typing
import logging
from pathlib import Path
import subprocess
from .command_file import CommandResult

_logger = logging.getLogger("local_command")

_nightskycam_local_command_file = Path("/opt/nightskycam/command.sh")


def _file_exists(fn):
    def check_file(path: Path):
        if not path.is_file():
            raise FileNotFoundError(f"file not found: {path}")
        return fn(path)

    return check_file


@_file_exists
def _has_content(path: Path):
    content = path.read_text()
    if content:
        return True
    return False


@_file_exists
def _delete_content(path: Path):
    open(path, "w").close()


@_file_exists
def _execute_file(path: Path):
    output = subprocess.run(["/bin/bash", f"{path}"], capture_output=True)
    result = CommandResult()
    result.filename = path.name
    result.return_code = output.returncode
    result.stdout = output.stdout.decode("utf-8")
    result.stderr = output.stderr.decode("utf-8")
    return result


def execute_local_command() -> typing.Optional[CommandResult]:
    try:
        has_content = _has_content(_nightskycam_local_command_file)
    except FileNotFoundError:
        _logger.debug(
            f"local command file {_nightskycam_local_command_file} not found, skipping"
        )
        return None
    if not has_content:
        _logger.debug(
            f"local command file {_nightskycam_local_command_file} has no content, skipping"
        )
        return None
    _logger.info(f"executing local command file {_nightskycam_local_command_file}")
    result = _execute_file(_nightskycam_local_command_file)
    _logger.debug(
        f"deleting command of local command file {_nightskycam_local_command_file}"
    )
    _delete_content(_nightskycam_local_command_file)
    return result
