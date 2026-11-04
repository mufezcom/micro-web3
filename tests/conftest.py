"""A local JSON-RPC server so tests exercise the real urllib path."""

import json
import threading
import time
from collections.abc import Callable, Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, cast

import pytest

from micro_web3 import RpcNode


class _Server(ThreadingHTTPServer):
    fake: "FakeRpc"


class FakeRpc:
    """A throwaway JSON-RPC endpoint bound to 127.0.0.1."""

    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []
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

    def close(self) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()
        self._thread.join(timeout=5)


class _Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)
        request = json.loads(raw)
        fake = cast(_Server, self.server).fake
        fake.requests.append(request)

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
