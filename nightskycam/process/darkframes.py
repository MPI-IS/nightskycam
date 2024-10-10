from pathlib import Path

import h5darkframes as dark
import nptyping as npt
from h5darkframes import substract


def darkframes(
    image: npt.NDArray, temperature: int, exposure: int, h5file: Path
) -> npt.NDArray:
    """
    Removes the darkframe, using a hdf5 darkframe file
    generated using
    [https://github.com/MPI-IS/h5darkframes](https://github.com/MPI-IS/h5darkframes)
    """
    h5file_ = Path(h5file)

    param = (temperature, exposure)

    with dark.ImageLibrary(h5file_) as il:
        try:
            neighbors = il.get_interpolation_neighbors(param)
        except ValueError:
            neighbors = [il.get_closest(param)]
        if param in neighbors:
            darkframe, _ = il.get(param)
        else:
            darkframe = il.generate_darkframe(param, neighbors)
        subimage = dark.substract(image, darkframe)

    return subimage
