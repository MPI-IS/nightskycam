import typing
import nptyping as npt
from pathlib import Path
import cv2


_cv2_params: typing.Dict[str, typing.Tuple[int, int]] = {
    ".tiff": (cv2.IMWRITE_TIFF_COMPRESSION, 1)  # 1: no compression
}


def _get_cv2_params(filename: str):
    for format_ in _cv2_params.keys():
        if filename.endswith(format_):
            return _cv2_params[format_]
    return None


def save(filepath: Path, data: npt.NDArray) -> None:
    folder = filepath.parent
    if not folder.exists():
        raise FileNotFoundError(
            f"fails to save image {filepath.name} to {folder}: " "folder not found"
        )
    params = _get_cv2_params(filepath.name)
    if params:
        cv2.imwrite(str(filepath), data, params=params)
    else:
        cv2.imwrite(str(filepath), data)


def display(label: str, data: npt.NDArray) -> None:
    cv2.imshow(label, data)
    cv2.waitKey(0)
    cv2.destroyAllWindows()
