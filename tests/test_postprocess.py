import time
import tempfile
import typing
import pytest
import toml
import cv2
import numpy as np
import nightskycam
from pathlib import Path


def test_convert_color():

    conversion_code = "COLOR_BAYER_BG2BGR"
    image_in = np.zeros((300,), np.uint16)
    image_out = nightskycam.utils.postprocess.convert_color(image_in, conversion_code)
    assert image_out.shape == (300, 1, 3)


def test_convert_color_then_size():

    config: typing.Dict[str, typing.Any] = {}
    config["steps"] = ["convert_color", "cv2_resize"]

    config["convert_color"]: typing.Dict[str, typing.Any] = {}
    config["convert_color"]["conversion_code"] = "COLOR_BAYER_RGGB2BGR"

    config["cv2_resize"]: typing.Dict[str, typing.Any] = {}
    config["cv2_resize"]["ratio"] = 2
    config["cv2_resize"]["interpolation"] = "INTER_NEAREST"

    image_in = np.zeros((300, 600), np.uint16)
    image_out = nightskycam.utils.postprocess.apply(image_in, config)

    assert image_out.shape == (150, 300, 3)
    assert image_out.dtype == np.uint16


def test_fileformat_write():

    image_in = np.zeros((150, 300, 3), np.uint16)
    fileformat = "tiff"
    meta = {"test": "test_fileformat_write"}
    config: typing.Dict[str, typing.Any] = {"IMWRITE_TIFF_COMPRESSION": 1}
    cv2params = nightskycam.skythreads.postprocess_thread._get_cv2params(config)

    image = nightskycam.cameras.images.Image(image_in, meta, filename="test")

    with tempfile.TemporaryDirectory() as tmp_dir_:
        tmp_dir = Path(tmp_dir_)
        image.save(tmp_dir, fileformat, cv2params=cv2params)

        files = list(tmp_dir.glob("*.tiff"))
        assert len(files) == 1
        assert str(files[0]).endswith("test.tiff")


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
        self.src_dir: typing.Optional[Path] = None
        self.dest_dir: typing.Optional[Path] = None


params: typing.Tuple[_TestConfig, ...] = (
    _TestConfig(
        _FileFormat("tiff", {"IMWRITE_TIFF_COMPRESSION": 1}),
        (
            _Step("convert_color", {"conversion_code": "COLOR_BAYER_RGGB2BGR"}),
            _Step("cv2_resize", {"ratio": 2, "interpolation": "INTER_NEAREST"}),
        ),
        (300, 600),
        (150, 300, 3),
    ),
    _TestConfig(
        _FileFormat("tiff", {"IMWRITE_TIFF_COMPRESSION": 32773}),
        (
            _Step("convert_color", {"conversion_code": "COLOR_BAYER_RGGB2BGR"}),
            _Step("cv2_resize", {"ratio": 2, "interpolation": "INTER_NEAREST"}),
        ),
        (600, 1200),
        (300, 600, 3),
    ),
    _TestConfig(
        _FileFormat("tiff", {}),
        (
            _Step("convert_color", {"conversion_code": "COLOR_BAYER_RGGB2BGR"}),
            _Step("cv2_resize", {"ratio": 2, "interpolation": "INTER_NEAREST"}),
        ),
        (60, 30),
        (30, 15, 3),
    ),
    _TestConfig(
        _FileFormat(
            "jpeg",
            {"IMWRITE_JPEG_QUALITY": "default", "IMWRITE_JPEG_RST_INTERVAL": 1},
        ),
        (
            _Step("convert_color", {"conversion_code": "COLOR_BAYER_RGGB2BGR"}),
            _Step("cv2_resize", {"ratio": 1, "interpolation": "INTER_NEAREST"}),
        ),
        (420, 540),
        (420, 540, 3),
    ),
    _TestConfig(
        _FileFormat("jpeg", {}),
        (
            _Step("convert_color", {"conversion_code": "COLOR_BAYER_RGGB2BGR"}),
            _Step("cv2_resize", {"ratio": 3}),
        ),
        (120, 30),
        (40, 10, 3),
    ),
)


@pytest.fixture(params=params)
def postprocess_setup(
    request,
) -> typing.Generator[
    typing.Tuple[nightskycam.skythreads.PostprocessThread, _TestConfig], None, None
]:

    src_dir_ = tempfile.TemporaryDirectory()
    dest_dir_ = tempfile.TemporaryDirectory()

    src_dir = Path(src_dir_.name)
    dest_dir = Path(dest_dir_.name)

    test_config: _TestConfig = request.param
    test_config.src_dir = src_dir
    test_config.dest_dir = dest_dir
    steps = [step.name for step in test_config.steps]

    main_config = {"period": 0.1}

    postp_config: typing.Dict[str, typing.Any] = {
        "src_dir": src_dir,
        "dest_dir": dest_dir,
        "fileformat": test_config.fileformat.fileformat,
        test_config.fileformat.fileformat: test_config.fileformat.cv2params,
        "steps": steps,
        "batch_size": 10,
    }
    for step in test_config.steps:
        postp_config[step.name] = step.config

    config: typing.Dict[str, typing.Any] = {}
    config["main"] = main_config
    config["nightskycam.skythreads.PostprocessThread"] = postp_config

    config_getter = nightskycam.configuration_getter.DictConfigurationGetter(config)

    config_error = nightskycam.skythreads.PostprocessThread.check_config(config_getter)
    if config_error is not None:
        raise ValueError(
            f"error in the configuration used for testing process: {config_error}"
        )

    instance = nightskycam.skythreads.PostprocessThread(config_getter)

    yield instance, test_config

    instance.on_exit()
    src_dir_.cleanup()
    dest_dir_.cleanup()


def test_postprocess_thread(postprocess_setup):

    postprocess, test_config = postprocess_setup

    postprocess.deploy_test()

    [f.unlink() for f in test_config.src_dir.glob("*")]
    [f.unlink() for f in test_config.dest_dir.glob("*")]

    src_image1 = np.zeros(test_config.src_shape, dtype=np.uint16)
    src_meta1 = {"type": "meta"}
    src_image2 = np.zeros(test_config.src_shape, dtype=np.uint16)
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

    dest_metas = list(test_config.dest_dir.glob("*.toml"))
    assert len(dest_metas) == 2

    with open(dest_metas[0], "r") as f:
        meta = toml.load(f)
        assert meta["type"] == "meta"

    dest_image = cv2.imread(str(dest_images[0]))
    assert dest_image.shape == test_config.expected_shape
