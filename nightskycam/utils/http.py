import os
import threading
import socketserver
from http import server
from pathlib import Path


class HttpServer:
    def __init__(self, folder: Path, port: int = 0) -> None:
        os.chdir(folder)
        Handler = server.SimpleHTTPRequestHandler
        self._httpd = socketserver.TCPServer(("", port), Handler)
        self._port = self._httpd.server_address[1]

    def get_port(self) -> int:
        return self._port

    def run(self) -> None:
        self._httpd.serve_forever()

    def start(self) -> None:
        self._thread = threading.Thread(target=self.run)
        self._thread.start()

    def stop(self) -> None:
        self._httpd.shutdown()
        self._thread.join()

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, e_type, e_value, e_traceback):
        self.stop()
