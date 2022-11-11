import toml
import typing
import tempfile
import numpy as np
import numpy.typing as npt
from pathlib import Path
import cv2

CV2Format = typing.Dict[str, int]
"""
A dictionary providing values of opencv2 save method 'params' key word argument,
e.g. {"IMWRITE_JPEG_QUALITY":95, "IMWRITE_JPEG_PROGRESSIVE":0}
"""

CV2Params = typing.List[typing.Tuple[int, int]]
"""
A configuration array for the 'params' key word argument 
of the opencv2 save method,
e.g [(cv2.IMWRITE_JPEG_QUALITY,95),(IMWRITE_JPEG_PROGRESSIVE,0)]
"""


Metadata = typing.Dict[str, typing.Any]


def display(label: str, data: npt.NDArray) -> None:
    cv2.imshow(label, data)
    cv2.waitKey(0)
    cv2.destroyAllWindows()


class Image:
    def __init__(
        self,
        data: npt.ArrayLike,
        metadata: Metadata,
        filename: typing.Optional[str] = None,
    ) -> None:
        self.filename: typing.Optional[str] = filename
        self.fileformat: typing.Optional[str] = None
        self.data: npt.ArrayLike = data
        self.metadata: Metadata = metadata

    def add_meta(self, key: str, more_meta: Metadata) -> None:
        self.metadata[key] = more_meta

    def save(
            self, target_dir: Path, fileformat: str = "npy",
            filename: typing.Optional[str]=None, cv2params: CV2Params = []
    ) -> None:

        if not target_dir.is_dir():
            raise FileNotFoundError(
                f"can not save image in {target_dir}: " "directory not found"
            )

        if filename is None and self.filename is None:
            raise ValueError(
                f"can not save image to {target_dir}: " "filename is not specified"
            )

        if filename is not None:
            self.filename = filename

        self.fileformat = fileformat

        with tempfile.TemporaryDirectory() as tmp_dir:

            tmp_data_file = Path(tmp_dir) / f"{self.filename}.{self.fileformat}"
            tmp_metadata_file = Path(tmp_dir) / f"{self.filename}.toml"

            if self.fileformat == "npy":
                np.save(tmp_data_file, self.data)
            else:
                if cv2params:
                    cv2.imwrite(str(tmp_data_file), self.data, params=cv2params)
                else:
                    cv2.imwrite(str(tmp_data_file), self.data)

            with open(tmp_metadata_file, "w") as f:
                toml.dump(self.metadata, f)

            data_file = target_dir / f"{self.filename}.{self.fileformat}"
            metadata_file = target_dir / f"{self.filename}.toml"

            tmp_data_file.rename(data_file)
            tmp_metadata_file.rename(metadata_file)
