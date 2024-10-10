"""
Module defining WebsocketReceiverMixin and WebsocketSenderMixin.
"""

import ssl
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from queue import Empty, Queue
from threading import Event, Lock, Thread
from typing import Any, Callable, Generator, List, Optional, Tuple, TypedDict

import websocket
from nightskyrunner.status import Status
from websocket_server import WebsocketServer


def _get_ssl_opt(cert_file: Path):
    return {"cert_reqs": ssl.CERT_REQUIRED, "ca_certs": str(cert_file)}


class WebsocketSenderMixin:
    """
    Convenience mixin for a class to be able to send
    websocket messages.

    ```python
    class A(WebsocketSenderMixin):
      def __init__(self):
        WebsocketSenderMixin.__init__(self)
    ```

    A has then the methods:

    - [WebsocketSenderMixin.send](send)
    - [WebsocketSenderMixin.sender_stop](sender_stop)
    - [WebsocketSenderMixin.sender_connected](sender_connected)

    Note that no websocket connection is initiated in the constructor.
    A websocket connection is open upon the first call to 'send'.
    If for any reason this connection closes, any following
    call to 'send' will attempt to reopen it.
    """

    def __init__(self):
        self._websocket = None
        self._url = None

    def _connect(
        self,
        server_url: str,
        status: Optional[Status] = None,
        cert_file: Optional[Path] = None,
        timeout: Optional[float] = 10.0,
    ) -> None:
        # creating a websocket connection, only if no
        # active connection or if the url of the server changed

        # there is no active connection, or the url of the
        # the server changed
        if self._url is None or self._url != server_url:
            # active connection, but url changed. Closing
            # the activate connection (which uses the "old" url)
            if self._url is not None:
                self.sender_stop()

            self._url = server_url

        # There is already a connection with the desired server,
        # exit
        elif self.sender_connected():
            return

        # We need to create a new connection
        if status is not None:
            status.activity(f"connecting to {server_url}")
        if cert_file:
            sslopt = _get_ssl_opt(cert_file)
        else:
            sslopt = {}

        try:
            self._websocket = websocket.create_connection(server_url, sslopt=sslopt)
        except ConnectionRefusedError:
            raise Exception(f"failed to connect to {server_url}")

    def _with_timeout(self, instance, fn_name: str, timeout: float, *args) -> Any:
        class _Output(TypedDict):
            value: bool
            error: Optional[Exception]
            out: Optional[Any]

        def _execute(instance, fn_name: str, output: _Output, *args) -> None:
            try:
                out = getattr(instance, fn_name)(*args)
            except Exception as e:
                output["error"] = e
                return
            else:
                output["value"] = True
                output["out"] = out

        output: _Output = {"value": False, "error": None, "out": None}
        thread = threading.Thread(
            target=_execute, args=(instance, fn_name, output, *args)
        )
        thread.start()
        thread.join(timeout)

        if not output["value"]:
            if output["error"]:
                raise output["error"]
            else:
                raise RuntimeError(
                    f"timeout on websocket.{fn_name}({args}) ({timeout} seconds)"
                )
        else:
            return output["out"]

    def sender_stop(self, timeout: float = 10.0) -> None:
        """
        Close the websocket connection.
        """
        if self._websocket is not None:
            try:
                self._with_timeout(self._websocket, "close", timeout)
            finally:
                self._websocket = None

    def _sender_connected(self) -> bool:
        if not hasattr(self, "_websocket"):
            return False
        if self._websocket is None:
            return False

        # the recv method needs to be called
        # for the connected attribute of
        # websocket to be updated
        try:
            self._websocket.ping("ping")
            self._websocket.settimeout(1e-10)
            self._websocket.recv()
        except websocket.WebSocketTimeoutException:
            pass
        except websocket.WebSocketConnectionClosedException:
            self._websocket = None
            return False
        if not self._websocket.connected:
            self._websocket = None
            return False
        self._websocket.settimeout(None)
        return True

    def sender_connected(self, timeout: float = 10.0) -> bool:
        """
        Returns True if a websocket connection is
        active, False otherwise.
        """
        return self._with_timeout(self, "_sender_connected", timeout)

    def send(
        self,
        server_url: str,
        message: str,
        nb_sent: int = 0,
        status: Optional[Status] = None,
        cert_file: Optional[Path] = None,
        timeout: float = 10.0,
    ) -> None:
        """
        Send the message to the websocket server at 'server_url'.
        If no websocket is open, a new one will be opened (if it fails,
        this method will be blocking for 'timeout' seconds).

        Arguments:
          server_url: of format "ws://*" or "wss://*"
          message: the message to send
          nb_sent: used recursively by this method to
            make it more robust. Do not use.
          status: if not None, its activity will be set
            (e.g. "connecting to server", "sending message")
          cert_file: if the websocket server requires it
          timeout: timeout on websocket connection attempt.

        Raises
          ConnectionRefusedError
        """
        self._connect(
            server_url,
            status=status,
            cert_file=cert_file,
            timeout=timeout,
        )
        if self._websocket is not None:
            if status is not None:
                status.activity("sending message")
            try:
                self._with_timeout(
                    self._websocket,
                    "send",
                    timeout,
                    message.encode(
                        "utf-8",
                    ),
                )
            except Exception as e:
                if nb_sent == 0:
                    self.send(
                        server_url,
                        message,
                        nb_sent=1,
                        cert_file=cert_file,
                    )
                else:
                    self.sender_stop(timeout)
                    raise e


class WebsocketReceiverMixin:
    """
    Convenience mixin for a class to be able to receive
    websocket messages.

    ```python
    class A(WebsocketReceiverMixin):
      def __init__(self):
        WebsocketSenderMixin.__init__(self)
    ```

    A has then the methods:
    - [WebsocketSenderMixin.get](get)
    - [WebsocketSenderMixin.receiver_stop](receiver_stop)
    - [WebsocketSenderMixin.receiver_connected](receiver_connected)

    Note that no websocket is created in the constructor.
    A websocket connection is open upon the first call to 'get'.
    If for any reason this connection closes, any following
    call to 'get' will attempt to reopen it.
    """

    def __init__(self) -> None:
        self._uri: Optional[str] = None
        self._cert_file: Optional[Path] = None
        self._messages: Queue[str] = Queue()
        self._wsapp: Optional[websocket.WebSocketApp] = None
        self._receive_thread: Optional[threading.Thread] = None
        self._connected: bool = False
        self._ws_running: bool = False
        self._ws_close_message: Optional[str] = None

    @contextmanager
    def _manager_running(self):
        self._ws_running = True
        yield None
        self._ws_running = False

    def receiver_connected(self) -> bool:
        """
        Returns True if the websocket is
        connected, False otherwise
        """
        return self._connected

    def _wait_for_connection(self, timeout=5.0, timewait=0.05) -> bool:
        """
        Returns True if a connection is already established or established
        within timeout.
        """
        ts = time.time()
        while time.time() - ts < timeout:
            if self._connected:
                return True
            time.sleep(timewait)
        return False

    def _receive(self) -> None:
        # runs the websocket application that will
        # fill the self._messages queue with messages
        # received via the websocket.

        if self._uri is None:
            return

        def _on_open(wsapp):
            self._connected = True

        def _on_close(wsapp, close_status_code, close_msg):
            self._connected = False
            if close_status_code or close_msg:
                self._ws_close_message = f"{close_status_code}: {close_msg}"

        def _on_message(wsapp, message):
            if message:
                self._messages.put(message)

        if self._cert_file:
            sslopt = _get_ssl_opt(self._cert_file)
        else:
            sslopt = {}

        if self._timeout:
            websocket.setdefaulttimeout(self._timeout)

        self._wsapp = websocket.WebSocketApp(
            self._uri,
            on_message=_on_message,
            on_close=_on_close,
            on_open=_on_open,
        )

        with self._manager_running():
            self._wsapp.run_forever(sslopt=sslopt)

    def _start(self) -> None:
        # start the websocket application which will fill "self._messages"
        # with message received via the websocket.

        self._receive_thread = threading.Thread(target=self._receive)
        self._receive_thread.start()

    def stop_websocket(self) -> None:
        """
        close any websocket connection
        (if any).
        """
        if self._wsapp:
            self._wsapp.keep_running = False
            self._wsapp.close()
        if self._receive_thread:
            self._receive_thread.join()
        self._wsapp = None
        self._receive_thread = None
        self._ws_running = False

    def receiver_stop(self) -> None:
        """
        Alias to stop_websocket.
        """
        self.stop_websocket()

    def _revive(
        self, uri: str, cert_file: Optional[Path], timeout: Optional[float]
    ) -> None:
        # restart a websocket connection if needed

        if self._uri is None or self._uri != uri:
            self.stop_websocket()
            self._timeout = timeout
            self._uri = uri
            self._cert_file = cert_file
        if not self._ws_running:
            self._timeout = timeout
            self._start()

    def get(
        self,
        uri: str,
        cert_file: Optional[Path] = None,
        timeout: Optional[float] = 1.0,
    ) -> List[str]:
        """
        At the first call, spawn a websocket application that will store
        in a queue any message it receives. Each call to 'get' will returns
        the current content of the queue (which is then emptied).

        If the websocket application was closed for any reason, calls to 'get'
        will attempt to revive it.

        Arguments:
          uri: address to the webserver, with format "ws://*" or "wss://*".
          cert_file: if required by the webserver.
          timeout: for websocket connection.

        Returns
          The list of messages received since the last call to 'get'

        Raises
          RuntimeError if no websocket connection could be opened.
        """

        self._revive(uri, cert_file=cert_file, timeout=timeout)
        if not self._wait_for_connection(timeout=timeout):
            raise RuntimeError(f"websocket disconnected: {self._ws_close_message}")
        r: List[str] = []
        while not self._messages.empty():
            r.append(self._messages.get(block=False))
        return r

    def __enter__(self):
        return self

    def __exit__(self, _, __, ___):
        self.stop_websocket()


@contextmanager
def websocket_server(
    port: int, host: str = "127.0.0.1"
) -> Generator[Tuple[Queue, Queue, Callable[[], int]], None, None]:
    """
    Spawn a local websocket server.
    This server is not well secured, to be used only
    for testing purposes.
    It returns two queues:
    - receive queue: messages received by this
      server will be added to the queue
    - send queue: messages added to this queue
      will be sent by the server via the websocket

    It also returns a function which will provide the number
    of clients currently connected.

    Usage:

    ```python
    port = 8765
    with websocket_server(port) as queues:
      queue_receive, queue_send, nb_clients = queues
      # printing the number of clients currently connected:
      print(nb_clients())
      # connecting to the server, and sending "hello"
      ws = websocket.create_connection(f"ws:://127.0.0.1:{port}")
      ws.send("hello")
      # the server receives "hello" and adds it to queue_receive
      time_start = time.time()
      while queue_receive.empty():
        time.sleep(0.05)
        if time.time() - time_start > 2.0:
          raise RuntimeError("no message received")
      print(queue_receive.get())  # prints "hello"
    ```

    or:

    ```python
    port = 8765
    with websocket_server(port) as queues:
        queue_receive, queue_send, nb_clients = queues
        # printing the number of clients currently connected:
        print(nb_clients())
        ws = websocket.create_connection(f"ws:://127.0.0.1:{port}")
        # the server will get this message from the queue
        # and send it to all connected socket
        queue_send.put("hello")
        # receiving the message sent by the server
        message = ws.recv()
        print(message)  # prints "hello"
    ```
    """

    class _Clients:
        _count: int = 0
        _lock = Lock()

        @classmethod
        def add(cls):
            with cls._lock:
                cls._count += 1

        @classmethod
        def remove(cls):
            with cls._lock:
                cls._count -= 1

        @classmethod
        def count(cls):
            with cls._lock:
                return cls._count

    def _new_client(client, server):
        _Clients.add()

    def _client_left(client, server):
        _Clients.remove()

    def nb_clients() -> int:
        """
        Returns the number of clients
        currently connected to the server.
        """
        return _Clients.count()

    def _message_handler(client, server, message):
        queue_receive.put(message)

    # Define a function to send messages from the queue
    def _send_messages():
        while not stop_event.is_set():
            try:
                msg = queue_send.get(timeout=0.1)
                server.send_message_to_all(msg)
                queue_send.task_done()
            except Empty:
                continue

    server = WebsocketServer(host=host, port=port)
    server.set_fn_message_received(_message_handler)
    server.set_fn_new_client(_new_client)
    server.set_fn_client_left(_client_left)

    queue_receive: Queue[str] = Queue()
    queue_send: Queue[str] = Queue()
    stop_event = Event()

    server_thread = Thread(target=server.run_forever)
    server_thread.start()

    send_thread = Thread(target=_send_messages)
    send_thread.start()

    try:
        yield queue_receive, queue_send, nb_clients
    finally:
        stop_event.set()
        server.shutdown_gracefully()
        server_thread.join()
        send_thread.join()
