"""Live smoke tests. Skipped unless ``MICRON_RPC_URL`` is set."""

import os

import pytest

from micro_web3 import Contract, RpcNode, eth_call, get_block_number, get_logs, try_aggregate

RPC_URL = os.environ.get("MICRON_RPC_URL")

pytestmark = pytest.mark.skipif(not RPC_URL, reason="MICRON_RPC_URL is not set")

USDC = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
ERC20_ABI = [
    {
        "type": "function",
        "name": "decimals",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"name": "", "type": "uint8"}],
    },
    {
        "type": "function",
        "name": "symbol",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"name": "", "type": "string"}],
    },
]


def _node() -> RpcNode:
    assert RPC_URL is not None
    return RpcNode(RPC_URL, timeout=10)


def test_live_is_connected_and_head():
    node = _node()
    assert node.is_connected()

    head = get_block_number(node)
    assert head > 0

    logs = get_logs(node, from_block=head, to_block=head)
    assert isinstance(logs, list)
    for log in logs[:5]:
        assert log["blockNumber"].startswith("0x")
        assert isinstance(log["topics"], list) and log["topics"]
        assert log["data"].startswith("0x")


def test_live_contract_call_and_multicall():
    node = _node()
    if int(node.request("eth_chainId"), 16) != 1:
        pytest.skip("mainnet-only contract fixture")

    contract = Contract(USDC, ERC20_ABI)
    assert contract.call(node, "decimals") == 6
    assert contract.call(node, "symbol") == "USDC"

    results = try_aggregate(
        node,
        [
            (USDC, contract.encode("decimals")),
            (USDC, contract.encode("symbol")),
        ],
    )
    decimals, symbol = results
    assert decimals is not None and symbol is not None
    assert contract.decode("decimals", [], decimals) == 6
    assert contract.decode("symbol", [], symbol) == "USDC"


def test_live_raw_eth_call():
    node = _node()
    payload = eth_call(node, USDC, "0x313ce567")
    assert payload.startswith("0x")
