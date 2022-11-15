import pytest
import tempfile
import typing
import nightskycam
import random
from pathlib import Path


@pytest.fixture
def http_server() -> typing.Generator[typing.Tuple[int, Path], None, None]:

    temp_dir_ = tempfile.TemporaryDirectory()
    temp_dir = Path(temp_dir_.name)
    server = nightskycam.utils.http.HttpServer(temp_dir)
    server.start()
    yield server.get_port(), temp_dir
    server.stop()
    temp_dir_.cleanup()


def test_list_config_files():

    with tempfile.TemporaryDirectory() as tmp_dir_:

        tmp_dir = Path(tmp_dir_)

        valid_filenames = [
            "nightskycam_config_0.toml",
            "nightskycam_config_1.toml",
            "nightskycam_config_2.toml",
            "nightskycam_config_31.toml",
        ]

        invalid_filenames = [
            "nightskycam_1.toml",
            "skygaler_config_1.toml",
            "nightskycam_config_a.to",
            "nightskycam_config_ca_1.toml",
        ]

        for filename in valid_filenames:
            assert nightskycam.configuration_file.is_valid_configuration_filename(
                filename
            )

        for filename in invalid_filenames:
            assert not nightskycam.configuration_file.is_valid_configuration_filename(
                filename
            )

        filenames = valid_filenames + invalid_filenames
        random.shuffle(filenames)

        for filename in filenames:
            with open(tmp_dir / filename, "w+") as f:
                f.write("test content")

        config_files = nightskycam.configuration_file.list_local_config_files(tmp_dir)
        assert len(config_files) == len(valid_filenames)
        for valid in valid_filenames:
            assert valid in config_files

        best_config_file = nightskycam.configuration_file.best_config_file(config_files)
        assert best_config_file == "nightskycam_config_31.toml"

        version = nightskycam.configuration_file.get_version_number(best_config_file)
        assert version == 31


def test_list_remote_config_files(http_server):

    port, remote_tmp_dir = http_server

    valid_filenames = [
        "nightskycam_config_0.toml",
        "nightskycam_config_1.toml",
        "nightskycam_config_2.toml",
        "nightskycam_config_11.toml",
    ]

    invalid_filenames = [
        "nightskycam_1.toml",
        "skygaler_config_a.toml",
        "nightskycam_conf_1.to",
        "nightskycam_config_ca_1.toml",
    ]

    filenames = valid_filenames + invalid_filenames
    random.shuffle(filenames)

    for filename in filenames:
        with open(remote_tmp_dir / filename, "w+") as f:
            f.write("test content")

    url = f"http://127.0.0.1:{port}"
    test_valid = nightskycam.configuration_file.is_valid_configuration_filename
    config_files = nightskycam.utils.remote_download.list_remote_files(
        url,3.,test_valid
    )

    assert len(config_files) == len(valid_filenames)
    for valid in valid_filenames:
        assert valid in config_files

    best_config_file = nightskycam.configuration_file.best_config_file(config_files)
    assert best_config_file == "nightskycam_config_11.toml"

    with tempfile.TemporaryDirectory() as local_tmp_dir_:
        local_tmp_dir = Path(local_tmp_dir_)
        nightskycam.utils.remote_download.download_file(
            url, best_config_file, local_tmp_dir, remote_tmp_dir
        )
        downloaded_file = local_tmp_dir / best_config_file
        assert downloaded_file.is_file()


def test_upgrade_config_file(http_server):

    port, remote_tmp_dir = http_server
    url = f"http://127.0.0.1:{port}"

    # creating some remote config files
    remote_config_files = [
        "nightskycam_config_1.toml",
        "nightskycam_config_2.toml",
    ]
    for filename in remote_config_files:
        with open(remote_tmp_dir / filename, "w+") as f:
            f.write(f"remote {filename}")

    with tempfile.TemporaryDirectory() as local_tmp_dir_:
        local_tmp_dir = Path(local_tmp_dir_)

        # creating some local config files
        local_config_files = [
            "nightskycam_config_1.toml",
            "nightskycam_config_4.toml",
            "nightskycam_config_2.toml",
            "nightskycam_config_3.toml",
        ]
        for filename in local_config_files:
            with open(local_tmp_dir / filename, "w+") as f:
                f.write(f"local {filename}")

        # setting the main config file (nightskycam.toml)
        # as a symlink to the best local config file
        best_filename = "nightskycam_config_4.toml"
        best_config_file = local_tmp_dir / best_filename
        current_config = local_tmp_dir / "nightskycam_config.toml"
        current_config.symlink_to(best_config_file)

        # upgrading the configuration file
        # note: best configuration file is currently local !
        nightskycam.skythreads.config_thread.upgrade_config_file(
            url, local_tmp_dir, tmp_folder=remote_tmp_dir
        )

        # all local configuration, except the best one, should have
        # been deleted
        for filename in [f for f in local_config_files if f != best_filename]:
            assert not (local_tmp_dir / filename).is_file()

        # best file should still be there
        assert best_config_file.is_file()

        # and it should be the original local file
        assert "local" in best_config_file.read_text()

        # current config should be a symlink
        current_config = local_tmp_dir / "nightskycam_config.toml"
        assert current_config.is_symlink()

        # to the correct best file
        assert "local" in current_config.read_text()
        assert best_filename in current_config.read_text()

        # creating a better file remote
        best_filename = "nightskycam_config_5.toml"
        with open(remote_tmp_dir / best_filename, "w+") as f:
            f.write(f"remote {best_filename}")

        # upgrading the configuration file
        # note: best configuration file is now remote !
        nightskycam.skythreads.config_thread.upgrade_config_file(
            url, local_tmp_dir, tmp_folder=remote_tmp_dir
        )

        # all original local configuration
        # should have been deleted
        for filename in local_config_files:
            assert not (local_tmp_dir / filename).is_file()

        # remote best file should now be local
        assert (local_tmp_dir / best_filename).is_file()

        # current config should be a symlink
        current_config = local_tmp_dir / "nightskycam_config.toml"
        assert current_config.is_symlink()

        # to the correct best file
        assert "remote" in current_config.read_text()
        assert best_filename in current_config.read_text()
