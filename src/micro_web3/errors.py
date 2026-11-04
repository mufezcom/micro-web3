"""Exception hierarchy.

Everything raised by :mod:`micro_web3` derives from :class:`RpcError` so call
sites can keep a single ``except RpcError`` (the replacement for
``web3.exceptions.Web3Exception``).
"""

from typing import Any


class RpcError(Exception):
    """Base class for every error raised by micro_web3."""


class RpcConnectionError(RpcError):
    """The node could not be reached, timed out, or spoke non JSON-RPC."""

    def __init__(
        self,
        message: str,
        *,
        endpoint_uri: str | None = None,
        status: int | None = None,
    ) -> None:
        self.endpoint_uri = endpoint_uri
        self.status = status
        super().__init__(message)


class RpcResponseError(RpcError):
    """The node answered with a JSON-RPC ``error`` object.

    Reverts arrive here: the message contains ``execution reverted`` and the
    revert payload (when the node provides it) is in :attr:`data`.
    """

    def __init__(self, code: int, message: str, data: Any = None) -> None:
        self.code = code
        self.message = message
        self.data = data
        text = f"{message} (code {code})"
        if data not in (None, "", "0x"):
            text = f"{text}: {data!r}"
        super().__init__(text)


class AbiError(RpcError):
    """An ABI definition, value, or encoded payload was invalid."""
