"""
Module defining the functions:

- read_files
- extend_meta
- save_meta
- save_npy
- save
- get_cv2_config
"""

import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import cv2
import nptyping as npt
import numpy as np
import tomli
import tomli_w

supported_file_formats: Tuple[str, ...] = ("jpeg", "tiff", "npy")


def read_files(folder: Path) -> Dict[str, List[str]]:
    """
    Read the files of a folder (non recursive) and returns
    a dictionary, e.g.:

    ```
    { 'npy' : ["filename1", "filename2"] , "toml": ["filename1"] }
    ```
    meaning the folder contains filename1.npy, filename1.toml
    and filename2.npy
    """
    files = [x for x in folder.glob("*") if x.is_file()]
    r: Dict[str, List[str]] = {}
    for f in files:
        try:
            r[f.suffix[1:]].append(f.stem)
        except KeyError:
            r[f.suffix[1:]] = [f.stem]
    return r


def extend_meta(metafile: Path, extra_meta: Dict[str, Any]) -> Dict[str, Any]:
    """
    metafile is expected to be a toml file. Add the extra meta data
    to the file.
    """
    with open(metafile, "rb") as f:
        content = tomli.load(f)
    for k, v in extra_meta.items():
        content[k] = v
    with open(metafile, "wb") as f:
        tomli_w.dump(content, f)
    return content


def save_meta(meta: Dict[str, Any], filename: str, target_dir: Path) -> None:
    """
    Save the meta data as toml file {target_dir}/{filename}.toml.
    """
    if not target_dir.is_dir():
        target_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=target_dir) as tmp_dir:
        tmp_metadata_file = Path(tmp_dir) / f"{filename}.toml"
        with open(tmp_metadata_file, "wb") as f:
            tomli_w.dump(meta, f)
        metadata_file = target_dir / f"{filename}.toml"
        tmp_metadata_file.rename(metadata_file)


def save_npy(
    img: npt.NDArray,
    meta: Dict[str, Any],
    filename: str,
    target_dir: Path,
) -> Tuple[Path, Path]:
    """
    Save the image and the metadata (npy and toml files)
    in a multiprocessing friendly manner
    """
    # multiprocessing friendly manner: first write the content
    # in a temp file, then move (rename) file to its "final" path,
    # overwritting the already exiting file (if any).

    if not target_dir.is_dir():
        target_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=target_dir) as tmp_dir:
        tmp_data_file = Path(tmp_dir) / f"{filename}.npy"
        tmp_metadata_file = Path(tmp_dir) / f"{filename}.toml"
        np.save(tmp_data_file, img)
        with open(tmp_metadata_file, "wb") as f:
            tomli_w.dump(meta, f)
        data_file = target_dir / f"{filename}.npy"
        metadata_file = target_dir / f"{filename}.toml"
        tmp_data_file.rename(data_file)
        tmp_metadata_file.rename(metadata_file)
        return data_file, metadata_file


def save(
    image: npt.NDArray,
    target_dir: Path,
    filename: str,
    fileformat: str,
    cv2params: Optional[Tuple[str, int, int]],
    meta: Dict[str, Any] = {},
) -> None:
    """
    Save the image and the meta data in the provided format,
    in a multiprocessing friendly manner
    """
    if not target_dir.is_dir():
        target_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=target_dir) as tmp_dir:
        tmp_data_file = Path(tmp_dir) / f"{filename}.{fileformat}"
        if cv2params:
            if cv2params is not None:
                cv2.imwrite(str(tmp_data_file), image, params=cv2params[1:])
                meta["cv2params"] = f"{cv2params[0]}: {cv2params[2]}"
            else:
                cv2.imwrite(str(tmp_data_file), image)
        else:
            cv2.imwrite(str(tmp_data_file), image)
        data_file = target_dir / f"{filename}.{fileformat}"
        tmp_data_file.rename(data_file)
        if meta:
            tmp_meta_file = Path(tmp_dir) / f"{filename}.toml"
            with open(tmp_meta_file, "wb") as f:
                tomli_w.dump(meta, f)
            meta_file = target_dir / f"{filename}.toml"
            tmp_meta_file.rename(meta_file)


def get_cv2_config(
    fileformat: str, jpeg_quality: int = 95
) -> Optional[Tuple[str, int, int]]:
    """
    Returns the proper parameters for saving images via opencv.
    If the fileformat is "tiff", these parameters will ensure
    no compression is applied. If the fileformat is jpeg, then
    the parameters will ensure the desired quality is applied during
    compression. None is returned for other fileformat.
    The parameters are returned in a format suitable for the
    [save]() function (cv2params argument).
    """
    if fileformat.lower() == "tiff":
        return (
            "CV2.IMWRITE_TIFF_COMPRESSION",
            cv2.IMWRITE_TIFF_COMPRESSION,
            1,
        )
    if fileformat.lower() == "jpeg":
        return (
            "CV2.IMWRITE_JPEG_QUALITY",
            cv2.IMWRITE_JPEG_QUALITY,
            jpeg_quality,
        )
    return None
