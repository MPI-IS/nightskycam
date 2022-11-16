import time
import typing
import pytest
import toml
import cv2
import numpy as np
import nightskycam


class _FileFormat:
    def __init__(self, fileformat: str, cv2params: typing.Dict[str, typing.Any]):
        self.fileformat: str = fileformat
        self.cv2params = cv2params


class _Step:
    def __init__(self, name: str, config: typing.Dict[str, typing.Any]):
        self.name = name
        self.config = config


_Shape = typing.Tuple[int, ...]


class _TestConfig:
    def __init__(
        self,
        fileformat: _FileFormat,
        steps: typing.Iterable[_Step],
        src_shape: _Shape,
        expected_shape: _Shape,
    ):
        self.fileformat = fileformat
        self.steps = steps
        self.src_shape = src_shape
        self.expected_shape = expected_shape


params: typing.List[_TestConfig] = []


@pytest.fixture(params=params)
def postprocess_run(
    request,
) -> typing.Generator[
    typing.Tuple[nightskycam.skythreads.PostprocessThread, _TestConfig], None, None
]:

    src_dir_ = tempfile.TemporaryDirectory()
    dest_dir_ = tempfile.TemporaryDirectory()

    src_dir = Path(src_dir_.name)
    dest_dir = Path(dest_dir_.name)

    test_config: _TestConfig = request.param
    steps: [step.step_name for step in test_config.steps]

    main_config = {"period": 0.1}

    postp_config = {
        "src_dir": src_dir,
        "dest_dir": test_dir,
        "fileformat": test_config.fileformat.fileformat,
        test_config.fileformat.fileformat: test_config.fileformat.cv2params,
        steps: steps,
    }
    for step in steps:
        postp_config[step.name] = step.config

    config["main"] = main_config
    config["nightskycam.skythreads.PostprocessThread"] = postp_config

    config_getter = nightskycam.configuration_getter.DictConfigurationGetter(config)

    nightskycam.skythreads.PostprocessThread.check_config(config_getter)

    instance = nightskycam.skythreads.PostprocessThread(config_getter, ntfy=False)

    yield instance, test_config

    instance.on_exit()
    src_dir_.cleanup()
    dest_dir_.cleanup()


def test_postprocess_thread(postprocess_config):

    postprocess, test_config = postprocess_config

    postprocess.deploy_test()

    shape = (test_config.src_shape[0] * test_config.src_shape[1],)
    src_image1 = np.ndarray(shape, dtype=np.uint16)
    src_meta1 = {"type": "meta"}
    src_image2 = np.ndarray(shape, dtype=np.uint16)
    src_meta2 = {"type": "meta"}

    np.save(test_config.src_dir / "image1.npy", src_image1)
    np.save(test_config.src_dir / "image2.npy", src_image2)
    with open(test_config.src_dir / "image1.toml", "w") as f:
        toml.dump(src_meta1, f)
    with open(test_config.src_dir / "image2.toml", "w") as f:
        toml.dump(src_meta2, f)

    postprocess._execute()

    time.sleep(1.0)

    dest_images = list(
        test_config.dest_dir.glob(f"*.{test_config.fileformat.fileformat}")
    )
    assert len(dest_images) == 2

    dest_metas = list(test_config.dest_dir.glob(f"*.toml"))
    assert len(dest_metas) == 2

    with open(dest_metas[0], "r") as f:
        meta = toml.load(f)
        assert meta["type"] == "meta"

    dest_image = cv2.imread(dest_images[0])
    assert dest_image.shape == test_config.expected_shape
