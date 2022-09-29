import typing
import logging
import time
from .skythread import SkyThread
from .types import Configuration
from .configuration_getter import ConfigurationGetter
from .running_threads import RunningThreads, skythreads_stop, get_skythreads
from .utils import ntfy

_logger = logging.getLogger("manager")


def deploy_tests(config_getter: ConfigurationGetter) -> None:
    """
    Instantiates classes of SkyThread (according to the keys of the
    configuration returned by config_getter) and calls their "deploy_test"
    methods. Raises a ValueError with an explicit error message if anything fails
    (instantiation of the SkyThreads or deploy test failing).
    """

    # the main configuration needs the keys 'period' (float) and id (int)
    # to be present
    main_config: Configuration = config_getter.get("main")
    if "period" not in main_config:
        raise ValueError(
            "the main configuration does not contain the key 'period' "
            "(required to deploy tests)"
        )
    try:
        float(main_config["period"])
    except ValueError:
        raise ValueError(
            "the main configuration contains the key 'period' but its "
            "value is not a float (required to deploy tests)"
        )
    # instantiating the skythreads requested by the configuration
    skythread_classes: typing.List[typing.Type[SkyThread]] = get_skythreads(
        config_getter.get_global()
    )
    skythreads = [class_(config_getter) for class_ in skythread_classes]

    # checking if each skythread "agrees" with its configuration
    config_errors: typing.Dict[str, str] = {}
    for skythread in skythreads:
        error = skythread.check_config(config_getter)
        if error is not None:
            config_errors[skythread.__class__.__name__] = error
    if config_errors:
        error_msg = "\n".join([f"{k}: {v}" for k, v in config_errors.items()])
        raise ValueError(error_msg)

    # having each skythread run its deployment test
    errors: typing.Dict[str, str] = {}
    for skythread in skythreads:
        try:
            skythread.deploy_test()
            print("---", skythread.__class__.__name__, ":\tSUCCESS")
        except Exception as e:
            print("---", skythread.__class__.__name__, f":\tFAILED | {e}")
            errors[skythread.__class__.__name__] = str(e)
    if errors:
        error_msg = "\n".join([f"{k}: {v}" for k, v in errors.items()])
        raise ValueError(error_msg)


class MainControl:
    def __init__(self):
        self.running = True

    def __enter__(self):
        return self

    def __exit__(self, e_type, e_value, e_traceback):
        self.running = False


def _ntfy(
    config_getter: ConfigurationGetter, title: str, tags: typing.List[str]
) -> None:
    try:
        ntfy_config = ntfy.publish_config(config_getter)
    except Exception as e:
        _logger.error(f"failed to read ntfy configuration from configuration file: {e}")
        return
    if ntfy_config is not None:
        url, topic = ntfy_config
        try:
            ntfy.publish(url, topic, 3, title, "", tags)
        except Exception as e:
            _logger.error(str(e))


def run(main_control: MainControl, config_getter: ConfigurationGetter) -> None:

    _logger.info("starting")

    _ntfy(config_getter, "nightskycam starting", ["milky_way"])

    # reading the configuration: how often should the main process
    # attempt to revive dead threads ?
    period = float(config_getter.get("main")["period"])

    # making sure the stop function
    # of all thread will be called before
    # exit
    with skythreads_stop():

        # running for as long as required or for as long
        # the configuration did not change
        while main_control.running:

            # starting / stopping skythreads based on the
            # current configuration
            RunningThreads.maintain(config_getter)

            # sleeping a bit
            try:
                time.sleep(period)
            except KeyboardInterrupt:
                _ntfy(config_getter, "nightskycam requested to stop", ["zap"])
                _logger.info("nightskycam requested to stop")
                break

    _logger.info("exit")
    _ntfy(config_getter, "nightskycam stopped", ["sunrise_over_mountains"])
