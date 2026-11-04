"""Multicall3 batching (``tryAggregate``)."""

from collections.abc import Sequence
from functools import lru_cache
from typing import Any

from .contract import Contract
from .rpc import RpcNode

__all__ = ["MULTICALL3_ADDRESS", "try_aggregate"]

MULTICALL3_ADDRESS = "0xcA11bde05977b3631167028862bE2a173976CA11"

_MULTICALL3_ABI: tuple[dict[str, Any], ...] = (
    {
        "type": "function",
        "name": "tryAggregate",
        "stateMutability": "view",
        "inputs": [
            {"name": "requireSuccess", "type": "bool"},
            {
                "name": "calls",
                "type": "tuple[]",
                "components": [
                    {"name": "target", "type": "address"},
                    {"name": "callData", "type": "bytes"},
                ],
            },
        ],
        "outputs": [
            {
                "name": "returnData",
                "type": "tuple[]",
                "components": [
                    {"name": "success", "type": "bool"},
                    {"name": "returnData", "type": "bytes"},
                ],
            },
        ],
    },
)


@lru_cache(maxsize=16)
def _multicall(address: str) -> Contract:
    return Contract(address, _MULTICALL3_ABI)


def try_aggregate(
    node: RpcNode,
    calls: Sequence[tuple[str | bytes, str | bytes]],
    block: int | str = "latest",
    address: str = MULTICALL3_ADDRESS,
) -> list[bytes | None]:
    """Run ``calls`` through Multicall3 ``tryAggregate(false, calls)``.

    Each call is ``(target, calldata)``. Returns one entry per call: the raw
    return data as ``bytes``, or ``None`` when that individual call reverted.
    """
    contract = _multicall(address)
    encoded = [(target, call_data) for target, call_data in calls]
    results = contract.call(node, "tryAggregate", [False, encoded], block)
    return [return_data if success else None for success, return_data in results]
