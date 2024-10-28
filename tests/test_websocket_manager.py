import time
from queue import Queue
from typing import List, Union

import pytest
from nightskycam.utils import websocket_manager as ws


def _wait_for_websocket_message(
    queue_receive: Queue, timeout: float = 5.0, timewait: float = 0.05
) -> str:
    # Wait for the queue not to be empty anymore.
    # If after timeout, the queue is still empty, a RuntimeError is raised.
    # Otherwise, an item of the queue is returned.
    time_start = time.time()
    while time.time() - time_start < timeout:
        if not queue_receive.empty():
            break
        time.sleep(timewait)
    if queue_receive.empty():
        raise RuntimeError(
            f"websocket queue receive did not receive any message (in a timeframe of {timeout})"
        )
    return queue_receive.get()


def _check_send_message(
    uri: str, sender: ws.WebsocketSenderMixin, queue_receive: Queue, message: str
) -> None:
    # have sender send a message, and checking the message found its way to their
    # server.
    assert queue_receive.empty()
    sender.send(uri, message, timeout=2.0)
    message_ = _wait_for_websocket_message(queue_receive, timeout=2.0)
    assert message_.strip() == message


def test_websocket_sender_mixin():
    """
    Test for [nightskycam.utils.websocket_manager.WebsocketSenderMixin]()
    """

    port = 8765
    uri = f"ws://127.0.0.1:{port}"

    sender = ws.WebsocketSenderMixin()

    # server not started, checking sender reports
    # not being connected and error on send
    assert not sender.sender_connected()
    with pytest.raises(Exception):
        sender.send(uri, "no server test", timeout=1.0)

    # checking the server connects to server and
    # can send messages.
    with ws.websocket_server(port) as ws_server:
        queue_receive, queue_send, nb_clients = ws_server
        for message in [f"s{index}" for index in range(3)]:
            _check_send_message(uri, sender, queue_receive, message)

    # server closed
    assert not sender.sender_connected()
    with pytest.raises(Exception):
        sender.send(uri, message, timeout=1.0)

    # checking the sender connects back successfully
    # when the server is started again
    with ws.websocket_server(port) as ws_server:
        queue_receive, queue_send, nb_clients = ws_server
        for message in [f"s{index}" for index in range(3)]:
            _check_send_message(uri, sender, queue_receive, message)

    # checking a sender can also connect to an already existing
    # server
    with ws.websocket_server(port) as ws_server:
        queue_receive, queue_send, nb_clients = ws_server
        other_sender = ws.WebsocketSenderMixin()
        for message in [f"s{index}" for index in range(3)]:
            _check_send_message(uri, other_sender, queue_receive, message)

    sender.sender_stop()


def _check_receive_messages(
    uri: str,
    receiver: ws.WebsocketReceiverMixin,
    queue_send: Queue,
    messages: Union[str, List[str]],
    timeout: float = 2.0,
) -> None:
    # have the server sending messages,
    # and checking these messages are received
    # by the receiver.

    if type(messages) is str:
        messages = [messages]

    # upon construction, the receiver does *not*
    # connect. It connects only once 'get' is called.
    receiver.get(uri, timeout=0.2)
    assert receiver.receiver_connected()

    # sending the messages
    for message in messages:
        queue_send.put(message)

    # waiting for the messages to be received by
    # the mixin
    received: List[str] = []
    time_start = time.time()
    while len(received) != len(messages):
        if time.time() - time_start > timeout:
            raise RuntimeError(
                f"WebsocketReceiverMixin only managed to receive {len(received)} message(s)"
                f"out of {len(messages)} expected message(s) before timeout was reached after {timeout} seconds"
            )
        received.extend(receiver.get(uri, timeout=0.2))
        time.sleep(0.05)

    # checking all messages have been received
    assert set([r.strip() for r in received]) == set(messages)


def test_connection_websocket_receiver_mixin():
    """
    Test for [nightskycam.utils.websocket_manager.WebsocketReceiverMixin]():
    checking an instance of WebsocketReceiverMixing connects and disconnects
    gracefully with a websocket server.
    """

    port = 8765
    uri = f"ws://127.0.0.1:{port}"

    with ws.WebsocketReceiverMixin() as receiver:
        for index in range(2):
            # no server running, so no connection and
            # error on "get"
            assert not receiver.receiver_connected()
            with pytest.raises(RuntimeError):
                receiver.get(uri, timeout=1.0)
            with ws.websocket_server(port) as ws_server:
                # server running, so connection established
                # and no error on 'get'
                _, __, nb_clients = ws_server
                receiver.get(uri)
                assert receiver.receiver_connected()
                assert nb_clients() == 1


def test_websocket_receiver_mixin():
    """
    Test for [nightskycam.utils.websocket_manager.WebsocketReceiverMixin]():
    checking an instance of WebsocketReceiverMixing receives messages
    sent by a websocket server.
    """

    port = 8765
    uri = f"ws://127.0.0.1:{port}"

    for _ in range(2):
        with ws.WebsocketReceiverMixin() as receiver:
            for __ in range(2):
                assert not receiver.receiver_connected()
                with ws.websocket_server(port) as ws_server:
                    queue_receive, queue_send, nb_clients = ws_server
                    messages = [f"r{index}" for index in range(3)]
                    _check_receive_messages(uri, receiver, queue_send, messages)
