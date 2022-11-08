import time
import typing
import logging
from ..types import Configuration
from ..utils.http import HttpServer
from ..skythread import SkyThread
from ..configuration_getter import ConfigurationGetter
from ..configuration_file import configuration_file_folder

logger = logging.getLogger("postprocess")


def _run_postprocess(
        filename: str,
        src_dir: Path,
        tmp_dir: Path,
        final_dir: Path,
        config: Configuration,
        cv2_all_formats: images.CV2AllFormats
)->None:
    # the raw image and related toml metadata
    data_file = src_dir / f"{filename}.npy"
    meta_file = src_dir / f"{filename}.toml"

    # the postprocess files / metadata will first be saved
    # in a tmp directory
    dest_data_file = tmp_dir / f"{filename}.{config['fileformat']}"
    dest_meta_file = tmp_dir / f"{filename}.toml"

    # reading the numpy data and applying the posprocess based
    # on the user configuration
    data  = np.load(datafile)
    postprocess_data, postprocess_metadata = postprocess.apply(
        data, config, dry_run=False
    )
    images.save(dest_data_file, postprocess_data, cv2_all_formats)

    # adding the postprocess metadata to the metadata
    metadata = toml.load(meta_file)
    metadata["postprocess"] = postprocess_metadata
    with open(dest_meta_file, 'w') as f:
        toml.dump(metadata, f)

    # moving the files to the final directory
    final_data_file = final_dir / f"{filename}.{config['fileformat']}"
    final_meta_file = final_dir / f"{filename}.toml"
    dest_data_file.rename(final_data_file)
    dest_meta_file.rename(final_meta_file)

    
def _run_all_postprocesses(
        src_dir: Path,
        tmp_dir: Path,
        final_dir: Path,
        config: Configuration,
        cv2_all_formats: images.CV2AllFormats
)->None:

    # all dumped image numpy array
    data_files = src_dir.glob("*.npy")

    # processing them one by one ...
    for df in data_files:
        # but only if there is already a related
        # metadata file
        metafile = src_dir / f"{df.stem}.toml" 
        if metafile.isfile():
            # applying the postprocess and
            # writing the files in final_dir
            _run_postprocess(
                df.stem, src_dir, tmp_dir, final_dir,
                config, cv2_all_formats
            )
            

    

class PostprocessThread(SkyThread):
    def __init__(
        self, config_getter: ConfigurationGetter, ntfy: typing.Optional[bool] = True
    ):
        super().__init__(config_getter, "postprocess", ntfy=ntfy)
        self._started = False

    @classmethod
    def check_config(cls, config_getter: ConfigurationGetter) -> typing.Optional[str]:
        config: Configuration = config_getter.get("PostprocessThread")
        pathkeys = ("postprocess_dir","tmp_dir","final_dir")
        for pathkey in pathkeys:
            try:
                config[pathkey]
            except KeyError:
                return f"failed to find the required key '{pathkey}'"
        for pathkey in pathkeys:
            try:
                Path(config[pathkey]).mkdir(parents=True, exist_ok=True)
            except Exception as e:
                return str(
                    f"the path provided for {pathkey} does not exists and "
                    f"could not be created: {e}"
                )
        try:
            config["fileformat"]
        except KeyError:
            return "failed to find the required key 'fileformat'"
        try:
            steps = config["steps"]
        except KeyError:
            return "failed to find the required key 'steps'"

        if not isinstance(steps,list):
            return "the value for the key 'steps' should be a list"

        postprocesses = [v for v in config.values()
                         if not v=="steps"]

        for step in steps:
            if not step in postprocesses:
                return str(
                    f"the postprocess {step} is required by steps "
                    f"({str(steps)}) but has no related configuration key"
                )
        
        return None

    def deploy_test(self) -> None:
        config = self._config_getter.get("PostprocessThread")
        testfile = Path(config["postprocess_dir"]) / "deploy_test.npy"
        data = np.zeros(200,400)
        np.save(testfile,data)
        

        with HttpServer(configuration_file_folder(), int(config["port"])):
            time.sleep(0.5)

    def on_exit(self) -> None:
        if self._server is not None:
            self._server.stop()

    def _execute(self) -> None:

        if not self._started:

            config = self._config_getter.get("HttpThread")
            port = int(config["port"])
            self._server = HttpServer(configuration_file_folder(), port)
            self._server.start()
            self._started = True
            self._status.set_misc("serving at port", str(config["port"]))
