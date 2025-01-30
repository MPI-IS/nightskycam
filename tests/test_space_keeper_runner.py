import random
import string
import tempfile
import time
from functools import partial
from pathlib import Path
from typing import Generator, List

import pytest
from nightskyrunner.config import Config
from nightskyrunner.status import State, wait_for_status

from nightskycam.space_keeper.runner import SpaceKeeperRunner
from nightskycam.space_keeper.utils import (
    convert_mb_to_bits,
    file_size,
    files_to_delete,
    free_space,
    to_GB,
)
from nightskycam.utils.test_utils import (
    ConfigTester,
    configuration_test,
    had_error,
    get_manager,
    runner_started,
    wait_for,
)

""" Module for testing the runner SpaceKeeper and its related utils """


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


def test_files_to_delete() -> None:
    """
    Testing files_to_delete
    """
    with tempfile.TemporaryDirectory() as tmp:
        files = [Path(tmp) / f"f{index}" for index in range(5)]
        for f in files:
            with open(f, "w") as f_:
                f_.write(" " * int(1e6))
            time.sleep(0.01)
        size = file_size(files[0])

        threshold = free_space() + size * 2

        to_delete = files_to_delete(Path(tmp), threshold)

        assert len(to_delete) == 2
        for index in (0, 1):  # i.e. older files
            assert files[index] in to_delete


def test_to_GB() -> None:
    """
    Testing to_GB
    """

    assert to_GB("1244MB") == pytest.approx(1.21484375, 1e-4)
    assert to_GB("1245688KB") == pytest.approx(1.1879806519, 1e-4)
    assert to_GB("124GB") == 124

    with pytest.raises(ValueError):
        to_GB("MB")

    with pytest.raises(ValueError):
        to_GB("115425")

    with pytest.raises(ValueError):
        to_GB("115425FB")


class _SpaceKeeperRunnerConfig:
    @classmethod
    def get_config(cls, folder: Path, unsupported: bool = False) -> Config:
        if unsupported:
            return {"folder": "/an/invalid/path", "threshold_MB": -1}
        else:
            return {
                "folder": str(folder),
                "threshold_MB": 100,
                "frequency": 10.0,
            }

    @classmethod
    def get_config_tester(cls, folder: Path) -> ConfigTester:
        return ConfigTester(
            cls.get_config(Path(str(folder)), unsupported=False),
            cls.get_config(Path(str(folder)), unsupported=True),
        )


def test_configuration(tmp_dir) -> None:
    """
    Testing instances of SpaceKeeperRunner behave correctly
    to changes of configuration.
    """

    config_tester = _SpaceKeeperRunnerConfig.get_config_tester(tmp_dir)
    configuration_test(SpaceKeeperRunner, config_tester, timeout=30.0)


def _create_file_with_size(
    folder_path: Path, filename: str, filesize_bits: int
) -> Path:
    filesize_bytes = filesize_bits // 8
    path = folder_path / filename

    # Create and open the file in write-binary ('wb') mode
    with open(path, "wb") as f:
        # Move the file pointer to the desired size minus one byte
        f.seek(filesize_bytes - 1)
        # Write a single null byte at this position
        f.write(b"\0")

    return path


def test_file_size(tmp_dir):
    """
    Testing file_size
    """
    filesizes = (8, 8**2, 8**3, 8**4)
    for filesize in filesizes:
        path = _create_file_with_size(tmp_dir, "testfile", filesize)
        assert file_size(path) == filesize


def _write_files(
    target_folder: Path, nb_files: int, filesize_bits: int
) -> List[Path]:
    r: List[Path] = []
    letters = string.ascii_letters
    for _ in range(nb_files):
        filename = "".join(random.choice(letters) for i in range(8))
        r.append(
            _create_file_with_size(target_folder, filename, filesize_bits)
        )
        # making sure files do not have the same timestamp
        time.sleep(0.01)

    return r


def _list_files(target_folder) -> List[Path]:
    r: List[Path] = []
    for item in target_folder.iterdir():
        if item.is_file():
            r.append(item.absolute())
    return r


def test_space_keeper_runner(tmp_dir, mocker) -> None:
    """
    Testing the space keeper runner deletes oldest files
    to keep disk space.
    """

    def _free_space(
        threshold_MB: int,
        filesize_bits: int,
        nb_files_ok: int,
        target_dir: Path,
    ) -> int:
        # this function will replace utils.free_space.
        # If the number of files contained by target dir is
        # below or equal nb_files_ok, it will return a value of
        # free space above the threshold.
        # Otherwise, it will return a value of free space below
        # the threshold, i.e. some files should be deleted.
        # Note: value returned based on the number of files,
        # does not take the real size of file into account.
        threshold_bits = convert_mb_to_bits(threshold_MB)
        nb_files = len(_list_files(target_dir))
        free_space_bits = threshold_bits + filesize_bits * (
            nb_files_ok - nb_files
        )
        return free_space_bits

    config: Config = _SpaceKeeperRunnerConfig.get_config(tmp_dir)
    threshold_MB = int(config["threshold_MB"])  # type: ignore
    filesize_bits = 12 * 8
    nb_files_ok = 5
    target_dir = tmp_dir

    _mock_free_space = partial(
        _free_space, threshold_MB, filesize_bits, nb_files_ok, target_dir
    )

    # free_space is mocked: results should not depend on the
    # disk space of the test server !

    mocked_free_space = mocker.patch(
        "nightskycam.space_keeper.utils._free_space",
        side_effect=_mock_free_space,
    )

    with get_manager((SpaceKeeperRunner, config)):
        # running an in stance of SpaceKeeperRunner
        wait_for(runner_started, True, args=(SpaceKeeperRunner.__name__,))
        wait_for_status(SpaceKeeperRunner.__name__, State.running, timeout=2.0)

        # checking the runner did not switch to error mode
        time.sleep(0.5)
        assert not had_error(SpaceKeeperRunner.__name__)

        # target folder is empty, nothing happening
        wait_for(lambda: mocked_free_space.call_count > 0, True)
        assert len(_list_files(tmp_dir)) == 0

        # target folder has some files, but free disk space above threshold
        ini_count = mocked_free_space.call_count
        first_files = _write_files(tmp_dir, nb_files_ok, filesize_bits)
        wait_for(lambda: mocked_free_space.call_count > ini_count + 5, True)
        assert len(_list_files(tmp_dir)) == nb_files_ok

        # target_folder has new files, now exceeding disk space !
        # the new files should be deleted
        nb_extra_files = 4
        ini_count = mocked_free_space.call_count
        new_files = _write_files(tmp_dir, nb_extra_files, filesize_bits)
        wait_for(lambda: mocked_free_space.call_count > ini_count + 5, True)
        remaining_files = _list_files(tmp_dir)
        assert len(remaining_files) == nb_files_ok
        assert set(remaining_files) == set(new_files + [first_files[-1]])
        # checking the runner did not switch to error mode
        assert not had_error(SpaceKeeperRunner.__name__)
