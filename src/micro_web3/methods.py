"""High-level RPC helpers: ``eth_call``, ``eth_getLogs``, block number."""

from collections.abc import Sequence
from typing import Any

from .addresses import to_checksum_address
from .errors import RpcError
from .rpc import RpcNode

_BLOCK_TAGS = frozenset({"latest", "earliest", "pending", "safe", "finalized"})


def to_quantity(value: int | str) -> str:
    """Normalise a block number or tag to a JSON-RPC quantity.

    Accepts ``int``, decimal strings, hex strings and block tags. Decimal input
    is accepted on purpose: it lets call sites keep Etherscan-shaped arguments
    and still emit valid ``eth_getLogs`` params.
    """
    if isinstance(value, bool):
        raise ValueError("block number must not be a bool")
    if isinstance(value, int):
        if value < 0:
            raise ValueError(f"negative block number: {value}")
        return hex(value)
    if not isinstance(value, str):
        raise ValueError(f"invalid block identifier: {value!r}")
    stripped = value.strip()
    if stripped in _BLOCK_TAGS:
        return stripped
    if stripped[:2].lower() == "0x":
        try:
            return hex(int(stripped, 16))
        except ValueError as exc:
            raise ValueError(f"invalid hex block number: {value!r}") from exc
    if stripped.isdigit():
        return hex(int(stripped))
    raise ValueError(f"invalid block identifier: {value!r}")


def eth_call(
    node: RpcNode,
    to: str | bytes,
    data: str | bytes,
    block: int | str = "latest",
) -> str:
    """Perform one ``eth_call`` and return the raw ``0x`` result."""
    result = node.request(
        "eth_call",
        [
            {"to": to_checksum_address(to), "data": _hex_data(data)},
            to_quantity(block),
        ],
    )
    if not isinstance(result, str):
        raise RpcError(f"eth_call returned {type(result).__name__}, expected hex string")
    return result


def get_logs(
    node: RpcNode,
    address: str | bytes | Sequence[str | bytes] | None = None,
    topics: Sequence[str | Sequence[str] | None] | None = None,
    from_block: int | str | None = None,
    to_block: int | str | None = None,
) -> list[dict[str, Any]]:
    """Perform ``eth_getLogs`` and return the node's raw JSON-RPC objects.

    No normalisation: ``blockNumber``, ``topics`` and ``data`` stay hex strings,
    identical to the Etherscan/Blockscout shapes.
    """
    params: dict[str, Any] = {}
    if address is not None:
        if isinstance(address, (str, bytes)):
            params["address"] = to_checksum_address(address)
        else:
            params["address"] = [to_checksum_address(item) for item in address]
    if topics is not None:
        params["topics"] = list(topics)
    if from_block is not None:
        params["fromBlock"] = to_quantity(from_block)
    if to_block is not None:
        params["toBlock"] = to_quantity(to_block)

    result = node.request("eth_getLogs", [params])
    if not isinstance(result, list):
        raise RpcError(f"eth_getLogs returned {type(result).__name__}, expected list")
    return result


def get_block_number(node: RpcNode) -> int:
    """Return the head block number."""
    block = node.request("eth_getBlockByNumber", ["latest", False])
    if not isinstance(block, dict):
        raise RpcError("eth_getBlockByNumber returned a non-object result")
    number = block.get("number")
    if isinstance(number, int):
        return number
    if isinstance(number, str):
        try:
            return int(number, 16)
        except ValueError as exc:
            raise RpcError(f"invalid block number from node: {number!r}") from exc
    raise RpcError(f"eth_getBlockByNumber result without number: {block!r}")


def _hex_data(value: str | bytes) -> str:
    if isinstance(value, (bytes, bytearray)):
        return "0x" + value.hex()
    if isinstance(value, str):
        if value[:2].lower() != "0x":
            return "0x" + value
        return value
    raise ValueError(f"invalid calldata type: {type(value).__name__}")
