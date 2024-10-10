"""
Module defining the StatusRunner
"""

from pathlib import Path
from typing import List, Optional

from nightskycam_serialization.status import (
    StatusRunnerEntries,
    serialize_status,
)
from nightskyrunner.config_getter import ConfigGetter
from nightskyrunner.runner import ThreadRunner, status_error
from nightskyrunner.status import Status, StatusDict
from nightskyrunner.wait_interrupts import RunnerWaitInterruptors

from ..utils.websocket_manager import WebsocketSenderMixin


@status_error
class StatusRunner(ThreadRunner, WebsocketSenderMixin):
    """
    All running instances of [nightskyrunner.runner.Runner] maintains
    up to date [nightskyrunner.status.Status](status) information, that is
    written in the shared memory. A StatusRunner reads this information,
    serializes it and sends it to a websocket server. This can be used for
    example to display the status of all the runners live to a visitor
    of a webpage.

    The required or supported configuration keys are:

    - "url": url of the websocket server, in format "ws://*" or "wss://*"
    - "cert_file": path to the server public certificate, if required
    - "system": the name of the nightskycam system this runner is operating
      on.

    The status is serialized as a python representation of a list of the dictionaries
    returned by [nightskyrunner.status.Status.get](), e.g.

    ```python
    # the message sent by the StatusRunner and received by the server
    message = websocket.get()
    status_info: list[dict[str,str]] = eval(message)
    ```
    """

    def __init__(
        self,
        name: str,
        config_getter: ConfigGetter,
        interrupts: RunnerWaitInterruptors = [],
        core_frequency: float = 1.0 / 0.005,
    ) -> None:
        super().__init__(
            name, config_getter, interrupts, core_frequency, stop_priority=10
        )
        WebsocketSenderMixin.__init__(self)

    def iterate(self) -> None:
        # reading the configuration
        config = self.get_config()
        try:
            cert_file = Path(str(config["cert_file"]))
        except KeyError:
            cert_file = None

        # informing users at which period status information
        # is sent
        period = 1.0 / float(str(config["frequency"]))
        self._status.entries(
            StatusRunnerEntries(update=f"every {period:.2f} second(s)")
        )

        # reading all status from the shared memory
        status: List[Status] = Status.retrieve_all()
        list_status: List[StatusDict] = [s.get() for s in status]

        # serialization
        token: Optional[str] = None
        try:
            token = str(config["token"])
        except KeyError:
            pass
        message = serialize_status(
            str(config["system"]), list_status, token=token
        )

        # sending it to the server, see:
        # nightskycam.utils.websocket_manager.WebsocketSenderMixin
        self.send(
            str(config["url"]),
            message,
            nb_sent=0,
            status=self._status,
            cert_file=cert_file,
        )

    def on_exit(self) -> None:
        # closing websocket connections
        self.sender_stop()
