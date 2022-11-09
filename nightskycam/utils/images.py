import typing
import nptyping as npt
from pathlib import Path
import cv2

CV2Format = typing.Dict[str,int] # e.g. {"IMWRITE_JPEG_QUALITY":95, "IMWRITE_JPEG_PROGRESSIVE":0}
CV2AllFormats = typing.Dict[str,CV2Options] # e.g. {"jpeg": {"IMWRITE_JPEG_QUALITY":95, "IMWRITE_JPEG_PROGRESSIVE":0}}
CV2KWARGS = typing.List[typing.Tuple[int, int]] # e.g [(cv2.IMWRITE_JPEG_QUALITY,95),(IMWRITE_JPEG_PROGRESSIVE,0)]

MetaData = typing.Mapping[str,typing.Any]

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


class Image:

    def __init__(self, data: npt.ArrayList, metadata: Metadata)->None:
        self.filename: typing.Optional[str] = None
        self.current_dir: typing.Optional[Path] = None
        self.fileformat: typing.Optional[str] = None
        self.data: np.ArrayLike = data
        self.metadata: Metadata = metadata
        

    def save(
            target_dir: Path,
            filename: typing.Optional[str] = None,
            fileformat: str = "npy",
            cv2_all_formats: CV2AllFormats = {}
    )->None:

        if not target_dir.is_dir():
            raise FileNotFoundError(
                f"can not save image in {target_dir}: "
                "directory not found"
            )

        if filename is None and self.filename is None:
            raise ValueError(
                f"can not save image to {target_dir}: "
                "filename is not specified"
            )

        if filename is not None:
            self.filename = filename

        self.fileformat = fileformat

        data_file = target_dir / f"{self.filename}.{self.fileformat}"
        metadata_file = target_dir / f"{self.filename}.toml"
        
        if self.fileformat == "npy":
            np.save(data_file, self.data)
        else:
            images.save(data_file, self.data, cv2_all_formats)

        with open(metadata_file,"w") as f:
            toml.dump(self.metadata,f)

        self.current_dir = target_dir
        
        
    def move(self, destination_dir: Path)->None:

        for attr in self.__slots__:
            if getattr(self,attr) is None:
                raise ValueError(
                    f"failed to move image to {destination_dir}: "
                    f"attribute {attr} is None"
                )

        if not destination_dir.is_dir():
            raise FileNotFoundError(
                f"can not move image {self.filename} to {destination_dir}: "
                "directory not found"
            )
        
        data_file = self.current_dir / f"{self.filename}.{self.fileformat}"
        meta_file = self.current_dir / f"{self.filename}.toml"

        if not data_file.is_file():
            raise FileNotFoundError(
                f"can not move image f{data_file} to {destination_dir}: "
                "file not found"
            )

        if not meta_file.is_file():
            raise FileNotFoundError(
                f"can not move image f{meta_file} to {destination_dir}: "
                "file not found"
            )

        dest_data_file = destination_dir / f"{self.filename}.{self.fileformat}"
        dest_meta_file = destination_dir / f"{self.filename}.toml"
        
        data_file.rename(dest_data_file)
        meta_file.rename(dest_meta_file)

    
