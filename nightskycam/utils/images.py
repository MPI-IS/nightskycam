import typing
import nptyping as npt
from pathlib import Path
import cv2

CV2Format = typing.Dict[str,int] # e.g. {"IMWRITE_JPEG_QUALITY":95, "IMWRITE_JPEG_PROGRESSIVE":0}
CV2AllFormats = typing.Dict[str,CV2Options] # e.g. {"jpeg": {"IMWRITE_JPEG_QUALITY":95, "IMWRITE_JPEG_PROGRESSIVE":0}}
CV2KWARGS = typing.List[typing.Tuple[int, int]] # e.g [(cv2.IMWRITE_JPEG_QUALITY,95),(IMWRITE_JPEG_PROGRESSIVE,0)]

def _get_cv2_args(cv2_format: CV2Format)->CV2KWARGS:
    r: CV2KWARGS = []
    for name,value in cv2_format.items():
        try:
            cv2_attr = getattr(cv2,name)
        except AttributeError as e:
            raise AttributeError(
                "file format configuration error: "
                f"{name} is not a supported attribute of opencv2"
            )
        r.append(cv2_attr,int(value))
    return r


def _get_cv2_params(filename: str, cv2_all_formats: CV2AllFormats)->CV2KWARGS:
    for format_ in cv2_all_formats.keys():
        if filename.endswith(format_):
            return _get_cv2_args(CV2AllFormats[format_])
    return None


def save(filepath: Path, data: npt.NDArray, cv2_all_formats: CV2AllFormats) -> None:
    folder = filepath.parent
    if not folder.exists():
        raise FileNotFoundError(
            f"fails to save image {filepath.name} to {folder}: " "folder not found"
        )
    params = _get_cv2_params(filepath.name,cv2_all_formats)
    if params:
        cv2.imwrite(str(filepath), data, params=params)
    else:
        cv2.imwrite(str(filepath), data)


def display(label: str, data: npt.NDArray) -> None:
    cv2.imshow(label, data)
    cv2.waitKey(0)
    cv2.destroyAllWindows()
