import typing
import pytest
import tempfile
import toml
import camera_zwo_asi
import nightskycam
from pathlib import Path


@pytest.fixture
def configuration_getter(
    request, scope="function"
) -> typing.Generator[
    nightskycam.configuration_getter.DictConfigurationGetter, None, None
]:

    # connecting to the camera, and
    # getting a config file out of it
    camera = camera_zwo_asi.Camera(0)
    with tempfile.TemporaryDirectory() as tmp_dir:
        toml_path = Path(tmp_dir) / "test.toml"
        camera.to_toml(toml_path)
        asizwo_config = toml.load(toml_path)

    # creating some temporary folders and add
    # them to the configuration
    dirs = [tempfile.TemporaryDirectory() for _ in range(3)]
    tmp_dir, final_dir, latest_dir = [d.name for d in dirs]
    asizwo_config["tmp_dir"] = tmp_dir
    asizwo_config["final_dir"] = final_dir
    asizwo_config["latest_dir"] = latest_dir
    asizwo_config["start_record"] = "None"
    asizwo_config["end_record"] = "None"

    # frequency at which pictures are taken
    asizwo_config["picture_every"] = 1

    # creating the configuration getter that will
    # return this config
    main_config: nightskycam.types.Configuration = {}
    thread_config: nightskycam.types.GlobalConfiguration = {
        "main": main_config,
        "AsiZwoThread": asizwo_config,
    }
    config_getter = nightskycam.configuration_getter.DictConfigurationGetter(thread_config)

    yield config_getter

    # cleaning up the tmp directories
    for d in dirs:
        d.cleanup()


def test_asizwo_thread_deploy(configuration_getter):
    """
    testing the method nightskycam.skythreads.AsiZwoThread.deploy_test
    """

    config_getter = configuration_getter

    # checking the config
    output = nightskycam.skythreads.AsiZwoThread.check_config(config_getter)
    assert output is None

    # checking deploy
    asizwo_thread = nightskycam.skythreads.AsiZwoThread(config_getter)
    output = asizwo_thread.deploy_test()
    assert output is None


def test_asizwo_thread_execute(configuration_getter):
    """
    testing the method nightskycam.skythreads.AsiZwoThread._execute
    """

    config_getter = configuration_getter

    # checking the config
    output = nightskycam.skythreads.AsiZwoThread.check_config(config_getter)
    assert output is None

    # getting the related folders
    config = config_getter.get("AsiZwoThread")
    tmp_dir = Path(config["tmp_dir"])
    final_dir = Path(config["final_dir"])
    latest_dir = Path(config["latest_dir"])

    # counting the number of files in each  folder
    def _nb_files():
        return [
            len(list(folder.glob("*"))) for folder in (tmp_dir, final_dir, latest_dir)
        ]

    # instantiating the thread
    asi_zwo_thread = nightskycam.skythreads.AsiZwoThread(config_getter)

    # executing. content of tmp folder is always empty (content is moved during process)
    # content of final are the latest image and meta data, same for latest
    asi_zwo_thread._execute(sleep=False)
    nb_tmp, nb_final, nb_latest = _nb_files()
    assert nb_tmp == 0
    assert nb_final == 2
    assert nb_latest == 2

    # files accumule in final, but the 2 files are overwritten in latest
    asi_zwo_thread._execute(sleep=False)
    nb_tmp, nb_final, nb_latest = _nb_files()
    assert nb_tmp == 0
    assert nb_final == 4
    assert nb_latest == 2

    # ...
    asi_zwo_thread._execute(sleep=False)
    nb_tmp, nb_final, nb_latest = _nb_files()
    assert nb_tmp == 0
    assert nb_final == 6
    assert nb_latest == 2
