"""Exception hierarchy.

Every error raised by :mod:`micro_web3` derives from :class:`MicroWeb3Error`, so
call sites can keep a single ``except MicroWeb3Error`` (the replacement for
``web3.exceptions.Web3Exception``).

:class:`RpcError` narrows that to transport failures; ABI, signature, address
and contract validation errors do not derive from it. The input-validation
errors also inherit the builtin exception they replaced (``ValueError``,
``TypeError``, ``AttributeError``, ``UnicodeEncodeError``), so existing
``except ValueError``-style handling keeps working.
"""

from typing import Any


class MicroWeb3Error(Exception):
    """Base class for every error raised by micro_web3."""


class RpcError(MicroWeb3Error):
    """A JSON-RPC transport failure: the request or response was unusable."""


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


class AbiError(MicroWeb3Error):
    """An ABI definition, value, or encoded payload was invalid."""


class SignatureError(MicroWeb3Error):
    """A message signature was malformed or no signer could be recovered."""


class AddressError(MicroWeb3Error, ValueError):
    """An address was not a 20-byte hex string or 20-byte value."""


class BlockNumberError(MicroWeb3Error, ValueError):
    """A block number or tag was not a valid JSON-RPC quantity."""


class CalldataError(MicroWeb3Error, ValueError):
    """Calldata was neither ``bytes`` nor a hex ``str``."""


class ContractError(MicroWeb3Error, ValueError):
    """A contract operation is impossible, e.g. calling one without an address."""


class FunctionNotFoundError(MicroWeb3Error, AttributeError):
    """The ABI has no function with the requested name.

    Inherits ``AttributeError`` so callers that fall back to another indexer on
    a missing function keep working.
    """


class ImmutableAbiTypeError(MicroWeb3Error, AttributeError):
    """A field of an immutable :class:`~micro_web3.abi.AbiType` was assigned or deleted."""


class MessageTypeError(MicroWeb3Error, TypeError):
    """A message was neither ``str`` nor ``bytes``."""


class SignatureTypeError(MicroWeb3Error, TypeError):
    """A signature was neither ``str`` nor ``bytes``."""


class MessageEncodingError(MicroWeb3Error, UnicodeEncodeError):
    """A ``str`` message could not be UTF-8 encoded (e.g. a lone surrogate)."""

    def __init__(self, cause: UnicodeEncodeError) -> None:
        UnicodeEncodeError.__init__(
            self,
            cause.encoding,
            cause.object,
            cause.start,
            cause.end,
            cause.reason,
        )
