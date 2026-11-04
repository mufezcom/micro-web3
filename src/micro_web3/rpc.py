"""JSON-RPC over the standard library.

One HTTP POST per call, no retries, no connection pooling: fallback across
nodes is the caller's job (see rotkehlchen's ``EthereumManager``).
"""

import itertools
import json
import urllib.error
import urllib.request
from collections.abc import Mapping, Sequence
from typing import Any

from .errors import RpcConnectionError, RpcError, RpcResponseError

__all__ = ["RpcNode"]

_DEFAULT_USER_AGENT = "micro-web3"


class RpcNode:
    """A single JSON-RPC endpoint."""

    __slots__ = ("_headers", "_ids", "endpoint_uri", "timeout")

    def __init__(
        self,
        endpoint_uri: str,
        *,
        timeout: float = 4.0,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        self.endpoint_uri = endpoint_uri
        self.timeout = timeout
        self._headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": _DEFAULT_USER_AGENT,
        }
        if headers:
            self._headers.update(headers)
        self._ids = itertools.count(1)

    def request(self, method: str, params: Sequence[Any] | Mapping[str, Any] | None = None) -> Any:
        """Perform one JSON-RPC call and return its ``result``.

        Raises :class:`RpcConnectionError` if the endpoint cannot be reached and
        :class:`RpcResponseError` if it answers with a JSON-RPC error object.
        """
        if params is None:
            params_list: list[Any] = []
        elif isinstance(params, Mapping):
            params_list = [params]
        else:
            params_list = list(params)

        request_id = next(self._ids)
        try:
            payload = json.dumps(
                {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params_list},
                separators=(",", ":"),
            ).encode()
        except (TypeError, ValueError) as exc:
            raise RpcError(f"cannot serialise JSON-RPC params for {method}: {exc}") from exc
        http_request = urllib.request.Request(
            self.endpoint_uri,
            data=payload,
            headers=self._headers,
            method="POST",
        )

        try:
            with urllib.request.urlopen(http_request, timeout=self.timeout) as response:
                body = response.read()
        except urllib.error.HTTPError as exc:
            body = _read_quietly(exc)
            parsed = _parse_json(body)
            if isinstance(parsed, dict) and isinstance(parsed.get("error"), dict):
                raise _response_error(parsed["error"]) from exc
            raise RpcConnectionError(
                f"HTTP {exc.code} from {self.endpoint_uri}: {_snippet(body)}",
                endpoint_uri=self.endpoint_uri,
                status=exc.code,
            ) from exc
        except (urllib.error.URLError, OSError) as exc:
            raise RpcConnectionError(
                f"cannot reach {self.endpoint_uri}: {exc}",
                endpoint_uri=self.endpoint_uri,
            ) from exc

        parsed = _parse_json(body)
        if not isinstance(parsed, dict):
            raise RpcError(
                f"invalid JSON-RPC response from {self.endpoint_uri}: {_snippet(body)}",
            )

        error = parsed.get("error")
        if error is not None:
            if not isinstance(error, dict):
                raise RpcError(f"malformed JSON-RPC error from {self.endpoint_uri}: {error!r}")
            raise _response_error(error)
        if "result" not in parsed:
            raise RpcError(f"JSON-RPC response without result from {self.endpoint_uri}")
        return parsed["result"]

    def is_connected(self) -> bool:
        """Probe the node with ``web3_clientVersion``; never raises."""
        try:
            version = self.request("web3_clientVersion")
        except (RpcError, OSError, ValueError):
            return False
        return isinstance(version, str) and version != ""

    def __repr__(self) -> str:
        return f"RpcNode({self.endpoint_uri!r}, timeout={self.timeout!r})"


def _response_error(error: Mapping[str, Any]) -> RpcResponseError:
    code = error.get("code")
    message = error.get("message", "")
    return RpcResponseError(
        code if isinstance(code, int) else -1,
        message if isinstance(message, str) else str(message),
        error.get("data"),
    )


def _parse_json(body: bytes) -> Any:
    try:
        return json.loads(body)
    except ValueError:
        return None


def _read_quietly(exc: urllib.error.HTTPError) -> bytes:
    try:
        return exc.read()
    except OSError:
        return b""


def _snippet(body: bytes, limit: int = 300) -> str:
    return body[:limit].decode("utf-8", "replace")
