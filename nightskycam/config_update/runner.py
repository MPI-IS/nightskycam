"""
Module defining ConfigUpdateRunner
"""

import random
import string
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import tomli_w
from nightskycam_serialization.config import deserialize_config_update
from nightskycam_serialization.status import ConfigRunnerEntries
from nightskyrunner.config import Config
from nightskyrunner.config_getter import ConfigGetter
from nightskyrunner.runner import ThreadRunner, status_error
from nightskyrunner.shared_memory import SharedMemory
from nightskyrunner.status import Level
from nightskyrunner.wait_interrupts import RunnerWaitInterruptors

from ..utils.formating import format_seconds
from ..utils.websocket_manager import WebsocketReceiverMixin


def _generate_random_string(length: int = 10) -> str:
    # generates a 10 characters long random string

    characters = string.ascii_letters + string.digits
    random_string = random.choices(characters, k=length)
    return "".join(random_string)


@status_error
class ConfigUpdateRunner(ThreadRunner, WebsocketReceiverMixin):
    """
    Runner for changing the configuration of other runners based on
    messages received via websocket connections.

    Each received messages is a python string representation of a tuple
    consisting of the following elements:
    1. name of the runner to update
    2. new configuration dictionary to use.

    This assumes the runner to update uses
    a [nightskyrunner.config_toml.DynamicTomlConfigGetter]() for getting
    its configuration (which is the default behavior).


    Configuration keys:

    - url: for connection to the websocket server.
    - cert_file: path to the certificate for connection to the websocket server.

    For developers:  under the hood, the new configuration is writen in a temporary
    toml file. The path to this file is the written in the shared memory.
    Instances of DynamicTomlConfigGetter checks at each iteration the shared memory,
    and if there the path to a new configuration toml file is shared, it overwrites
    their current configuration file with this file.
    See [nightskyrunner.config_toml.DynamicTomlConfigGetter.update]().


    """

    def __init__(
        self,
        name: str,
        config_getter: ConfigGetter,
        interrupts: RunnerWaitInterruptors = [],
        core_frequency: float = 1.0 / 0.005,
    ) -> None:
        super().__init__(name, config_getter, interrupts, core_frequency)
        WebsocketReceiverMixin.__init__(self)
        self._updated: Dict[str, float] = {}
        self._issues: Dict[str, str] = {}
        self._update_messages: Dict[str, str] = {}
        self._time_start = time.time()

    def on_exit(self) -> None:
        self.stop_websocket()

    def _track_updates(
        self,
        runner_name: str,
        error: Optional[str] = None,
        differences: Optional[str] = None,
    ) -> None:
        # for keeping track of all the configuration
        # updates this instance performed.

        self._updated[runner_name] = time.time()
        if error is None:
            try:
                del self._issues[runner_name]
            except KeyError:
                pass
            if differences:
                self._update_messages[runner_name] = differences
            else:
                try:
                    del self._update_messages[runner_name]
                except KeyError:
                    pass
        else:
            self._issues[runner_name] = error

    def _update_status(self) -> None:
        # All configuration updates are "saved" in
        # the class variables _updated, _issues, and
        # _update_messages. This function "transfers"
        # these information in the status.

        d = ConfigRunnerEntries()
        d["updates"] = {}
        t = time.time()

        for runner_name, time_ in self._updated.items():
            update: Optional[str] = None
            time_diff = format_seconds(t - time_)
            error: Optional[str]
            try:
                error = self._issues[runner_name]
            except KeyError:
                error = None
            if error is None:
                try:
                    differences = self._update_messages[runner_name]
                    differences = f":\n{differences}"
                except KeyError:
                    differences = ""
                update = f"updated {time_diff} ago{differences}"
            else:
                update = f"update failed {time_diff} ago: {error}"
            if update:
                d["updates"][runner_name] = update
        if d["updates"]:
            self._status.entries(d)

    def _config_differences(
        self, previous: Config, updated: Dict[str, Any]
    ) -> Optional[str]:
        # "compute" the differences between previous and
        # "updated". The returned string is a summary
        # of these differences.

        r: List[str] = []
        pkeys = set(previous.keys())
        ukeys = set(updated.keys())
        pkeys_only = pkeys - ukeys
        ukeys_only = ukeys - pkeys
        ckeys = pkeys & ukeys
        for k in pkeys_only:
            r.append(f"{k}: {previous[k]} -> None")
        for k in ukeys_only:
            r.append(f"{k}: None -> {updated[k]}")
        for k in ckeys:
            if previous[k] != updated[k]:
                r.append(f"{k}: {previous[k]} -> {updated[k]}")
        if not r:
            return "no changes detected"
        return "\n".join(r)

    def iterate(self) -> None:
        # reading configuration
        config = self.get_config()
        cert_file: Optional[Path] = None
        try:
            cert_file = Path(str(config["cert_file"]))
        except KeyError:
            pass

        token: Optional[str] = None
        try:
            token = str(config["token"])
        except KeyError:
            pass

        # getting messages received via websockets
        messages = WebsocketReceiverMixin.get(
            self, str(config["url"]), cert_file=cert_file
        )

        for message in messages:
            # which runner should be updated with which config
            runner_name, new_config = deserialize_config_update(
                message, token=token
            )

            # getting the current configuration used by this runner.
            # This is for checking the differences with the new confuration.
            try:
                current_config = eval(SharedMemory.get(runner_name)["config"])
            except KeyError:
                continue
            else:
                # will be given a value if the received configuration can
                # not be dumped in toml format
                error: Optional[str] = None

                # will list the difference between the current and the new
                # configurations.
                differences: Optional[str] = None

                # writting the new configuration in a toml file
                filepath = Path("/tmp") / f"{_generate_random_string()}.toml"
                try:
                    with open(filepath, "wb") as f:
                        tomli_w.dump(new_config, f)
                except Exception as e:
                    self._status.set_issue(
                        str(
                            "failed to update configuration "
                            f"for {runner_name}: {e}"
                        )
                    )
                    error = str(e)
                else:
                    self.log(
                        Level.info,
                        f"updating configuration for {runner_name}",
                    )
                    # "computing" the differences between the current and the
                    # new config (will be shared in the status, to keep the
                    # user updated via the website)
                    differences = self._config_differences(
                        current_config, new_config
                    )

                    # sharing the path the new config file with the runner, which will
                    # overwrite its own configuration file.
                    SharedMemory.get(runner_name)["path"] = filepath

                # keeping all configuration update in memory (so that they can be
                # shared in the status)
                self._track_updates(
                    runner_name, error=error, differences=differences
                )

        # sharing the configuration updateds in the status
        self._update_status()
