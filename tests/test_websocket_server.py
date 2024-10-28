"""
Tests for [nightksycam.websocket_manager.websocket_server](websocket_server)
"""

import time

import websocket
from nightskycam.utils.websocket_manager import websocket_server

_URL = "127.0.0.1"
_PORT = 8765
_URI = f"ws://{_URL}:{_PORT}"


def test_websocket_server_receive() -> None:
    """
    Testing that the server can receive messages
    """
    with websocket_server(_PORT) as queues:
        queue_receive, queue_send, nb_clients = queues
        assert nb_clients() == 0
        ws = websocket.create_connection(_URI)
        assert nb_clients() == 1
        ws.send("hello")
        time_start = time.time()
        while queue_receive.empty():
            time.sleep(0.05)
            if time.time() - time_start > 2.0:
                raise RuntimeError("message not received")
        assert queue_receive.get() == "hello"


def test_websocket_server_send() -> None:
    """
    Testing that the server can send messages
    """
    with websocket_server(_PORT) as queues:
        queue_receive, queue_send, nb_clients = queues
        assert nb_clients() == 0
        ws = websocket.create_connection(_URI)
        assert nb_clients() == 1
        queue_send.put("hello")
        message = ws.recv()
        assert message == "hello"
