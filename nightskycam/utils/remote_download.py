import os
import typing
import logging
import requests
import wget
from pathlib import Path
from bs4 import BeautifulSoup as bsoup


_logger = logging.getLogger("download")


def list_remote_files(
    url: str, timeout: typing.Optional[float], is_valid: typing.Callable[[str], bool]
) -> typing.List[str]:
    """
    List all the valid files (i.e. is_valid(filename) returns True)
    that can be found at a remote location.
    """
    if timeout is not None:
        try:
            page = requests.get(url, timeout=timeout).text
        except requests.ConnectTimeout:
            raise ValueError(f"failed to connect to {url} with timeout {timeout}")
    else:
        page = requests.get(url).text
    soup = bsoup(page, "html.parser")
    nodes = soup.find_all("a")
    filenames = [node.get("href") for node in nodes]
    valid_filenames = [filename for filename in filenames if is_valid(filename)]
    return valid_filenames


def download_file(
    url: str,
    filename: str,
    target_folder: Path,
    tmp_folder: typing.Optional[Path] = None,
) -> None:
    total_url = f"{url}/{filename}"
    if not target_folder.is_dir():
        raise FileNotFoundError(
            f"failed to download {total_url} to {target_folder}: " f"folder not found"
        )
    if tmp_folder is not None:
        if not tmp_folder.is_dir():
            raise FileNotFoundError(
                f"failed to download {total_url} to {tmp_folder}: " f"folder not found"
            )
        os.chdir(tmp_folder)
    else:
        os.chdir(target_folder)
    try:
        wget.download(total_url, bar=None)
    except Exception as e:
        raise RuntimeError(f"failed to download {total_url} to {target_folder}: {e}")
    if not (Path(os.getcwd()) / filename).is_file():
        raise RuntimeError(
            f"failed to download {total_url} to {os.getcwd()}: " f"(unknown reason)"
        )
    if target_folder is not None:
        (Path(os.getcwd()) / filename).rename(target_folder / filename)
