"""A local JSON-RPC server so tests exercise the real HTTP path."""

import contextlib
import json
import socket
import sys
import threading
import time
from collections.abc import Callable, Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, cast

import pytest

from micro_web3 import RpcNode


class _Server(ThreadingHTTPServer):
    fake: "FakeRpc"

    def handle_error(self, request: Any, client_address: Any) -> None:
        # A client hanging up on a keep-alive connection is not a test failure.
        if not isinstance(sys.exc_info()[1], ConnectionError):
            super().handle_error(request, client_address)


class FakeRpc:
    """A throwaway JSON-RPC endpoint bound to 127.0.0.1."""

    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []
        self.client_ports: list[int] = []
        self.connections: list[socket.socket] = []
        self.extra_headers: dict[str, str] = {}
        self.responder: Callable[[dict[str, Any]], dict[str, Any]] = lambda request: {
            "result": "0x1",
        }
        self.status = 200
        self.raw_body: bytes | None = None
        self.delay = 0.0
        self._httpd = _Server(("127.0.0.1", 0), _Handler)
        self._httpd.fake = self
        self._thread = threading.Thread(
            target=self._httpd.serve_forever,
            kwargs={"poll_interval": 0.01},
            daemon=True,
        )
        self._thread.start()

    @property
    def url(self) -> str:
        host, port = self._httpd.server_address[:2]
        return f"http://{host}:{port}"

    def node(self, **kwargs: Any) -> RpcNode:
        return RpcNode(self.url, **kwargs)

    def drop_connections(self) -> None:
        """Close every open client socket, as a server does with idle keep-alives."""
        for connection in self.connections:
            with contextlib.suppress(OSError):
                connection.shutdown(socket.SHUT_RDWR)

    def close(self) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()
        self._thread.join(timeout=5)


class _Handler(BaseHTTPRequestHandler):
    # HTTP/1.1 keeps connections open, so tests go through pooled sockets.
    protocol_version = "HTTP/1.1"

    def setup(self) -> None:
        super().setup()
        cast(_Server, self.server).fake.connections.append(self.connection)

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)
        request = json.loads(raw)
        fake = cast(_Server, self.server).fake
        fake.requests.append(request)
        fake.client_ports.append(self.client_address[1])

        if fake.delay:
            time.sleep(fake.delay)

        if fake.raw_body is not None:
            body = fake.raw_body
            status = fake.status
        else:
            response = {"jsonrpc": "2.0", "id": request.get("id"), **fake.responder(request)}
            body = json.dumps(response).encode()
            status = fake.status

        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        for name, value in fake.extra_headers.items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        pass


@pytest.fixture
def rpc() -> Iterator[FakeRpc]:
    fake = FakeRpc()
    try:
        yield fake
    finally:
        fake.close()
