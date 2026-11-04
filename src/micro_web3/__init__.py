"""micro-web3: a small Ethereum JSON-RPC + ABI client.

Replaces the web3.py surface used by the rotki web backend: JSON-RPC transport,
calldata encoding, output decoding, log queries and Multicall3 batching.

    >>> from micro_web3 import Contract, RpcNode
    >>> node = RpcNode('https://ethereum-rpc.publicnode.com', timeout=4)
    >>> node.is_connected()
    True
    >>> contract = Contract('0xA0b8...eB48', erc20_abi)
    >>> contract.call(node, 'decimals')
    6
"""

from .abi import (
    AbiType,
    canonical,
    decode,
    decode_outputs,
    encode,
    encode_call,
    find_function,
    parse_type,
)
from .addresses import is_address, to_checksum_address
from .contract import Contract
from .errors import AbiError, RpcConnectionError, RpcError, RpcResponseError
from .methods import eth_call, get_block_number, get_logs, to_quantity
from .multicall import MULTICALL3_ADDRESS, try_aggregate
from .rpc import RpcNode

__version__ = "0.1.0"

__all__ = [
    "MULTICALL3_ADDRESS",
    "AbiError",
    "AbiType",
    "Contract",
    "RpcConnectionError",
    "RpcError",
    "RpcNode",
    "RpcResponseError",
    "__version__",
    "canonical",
    "decode",
    "decode_outputs",
    "encode",
    "encode_call",
    "eth_call",
    "find_function",
    "get_block_number",
    "get_logs",
    "is_address",
    "parse_type",
    "to_checksum_address",
    "to_quantity",
    "try_aggregate",
]
