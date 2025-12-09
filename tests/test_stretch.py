import numpy as np
import pytest

from nightskycam.process import stretch

_shape = (2822, 4144, 3)


@pytest.fixture
def random_image():
    return np.random.randint(low=0, high=65536, size=_shape, dtype=np.uint16)


@pytest.mark.parametrize("method", stretch.stretch_methods)
def test_stretch(random_image, method):
    """
    Test the stretch method on an image of the same shape and type
    as the one taken by an AsiZwo camera.
    """
    image = stretch.stretch(random_image, method)
    assert image.shape == _shape
    assert image.dtype == np.uint16


def test_stretch_raise_value_error(random_image):
    """
    Testing that a ValueError is raised if an invalid
    stretching method is requested.
    """
    with pytest.raises(ValueError):
        stretch.stretch(random_image, "NotAValidStretchMethod")
