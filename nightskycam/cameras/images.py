import typing
import nptyping as npt
from pathlib import Path
import cv2

MetaData = typing.Mapping[str, typing.Any]


def display(label: str, data: npt.NDArray) -> None:
    cv2.imshow(label, data)
    cv2.waitKey(0)
    cv2.destroyAllWindows()


class Image:
    def __init__(
        self,
        data: npt.ArrayList,
        metadata: Metadata,
        filename: typing.Optional[str] = None,
    ) -> None:
        self.filename: typing.Optional[str] = filename
        self.fileformat: typing.Optional[str] = None
        self.data: np.ArrayLike = data
        self.metadata: images.Metadata = metadata

    def add_meta(self, key: str, more_meta: images.Metadata) -> None:
        self.metadata[key] = more_meta

    def save(
        target_dir: Path, fileformat: str = "npy", cv2_all_formats: CV2AllFormats = {}
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
                    cv2.imwrite(str(tmp_data_file), data, params=cv2params)
                else:
                    cv2.imwrite(str(tmp_data_file), data)

            with open(tmp_metadata_file, "w") as f:
                toml.dump(self.metadata, f)

            data_file = target_dir / f"{self.filename}.{self.fileformat}"
            metadata_file = target_dir / f"{self.filename}.toml"

            tmp_data_file.rename(data_file)
            tmp_metadata_file.remame(metadata_file)
