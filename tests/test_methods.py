import pytest

from micro_web3 import (
    RpcError,
    eth_call,
    get_block_number,
    get_logs,
    to_checksum_address,
    to_quantity,
)

ADDRESS = "0x52908400098527886e0f7030069857d2e4169ee7"
TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"


def test_eth_call_builds_rpc_params(rpc):
    payload = (18).to_bytes(32, "big")
    rpc.responder = lambda request: {"result": "0x" + payload.hex()}
    node = rpc.node()

    result = eth_call(node, ADDRESS, "0x313ce567", block=123)

    assert result == "0x" + payload.hex()
    params = rpc.requests[0]["params"]
    assert rpc.requests[0]["method"] == "eth_call"
    assert params[0] == {"to": to_checksum_address(ADDRESS), "data": "0x313ce567"}
    assert params[1] == hex(123)


def test_eth_call_accepts_bytes_calldata(rpc):
    rpc.responder = lambda request: {"result": "0x"}
    eth_call(rpc.node(), ADDRESS, b"\x31\x3c\xe5\x67")
    assert rpc.requests[0]["params"][0]["data"] == "0x313ce567"


def test_eth_call_rejects_non_string_result(rpc):
    rpc.responder = lambda request: {"result": 42}
    with pytest.raises(RpcError):
        eth_call(rpc.node(), ADDRESS, "0x")


def test_get_logs_preserves_raw_hex_shape(rpc):
    raw_logs = [
        {
            "address": "0x" + "ab" * 20,
            "topics": [TOPIC, "0x" + "00" * 32],
            "data": "0x" + "ff" * 32,
            "blockNumber": "0x10",
            "blockHash": "0x" + "cd" * 32,
            "transactionHash": "0x" + "ef" * 32,
            "transactionIndex": "0x0",
            "logIndex": "0x1",
            "removed": False,
        },
    ]
    rpc.responder = lambda request: {"result": raw_logs}

    logs = get_logs(rpc.node(), address=ADDRESS, topics=[TOPIC], from_block="0", to_block="16")
    assert logs == raw_logs


def test_get_logs_translates_params(rpc):
    rpc.responder = lambda request: {"result": []}
    get_logs(rpc.node(), address=ADDRESS, topics=[[TOPIC]], from_block=0, to_block="0x0010")

    params = rpc.requests[0]["params"][0]
    assert params == {
        "address": to_checksum_address(ADDRESS),
        "topics": [[TOPIC]],
        "fromBlock": "0x0",
        "toBlock": "0x10",
    }


def test_get_logs_omits_unset_filters(rpc):
    rpc.responder = lambda request: {"result": []}
    get_logs(rpc.node())
    assert rpc.requests[0]["params"] == [{}]


def test_get_logs_rejects_non_list_result(rpc):
    rpc.responder = lambda request: {"result": {}}
    with pytest.raises(RpcError):
        get_logs(rpc.node())


def test_get_block_number(rpc):
    rpc.responder = lambda request: {"result": {"number": "0x10"}}
    node = rpc.node()

    assert get_block_number(node) == 16
    assert rpc.requests[0]["method"] == "eth_getBlockByNumber"
    assert rpc.requests[0]["params"] == ["latest", False]


def test_get_block_number_rejects_bad_payloads(rpc):
    rpc.responder = lambda request: {"result": "nope"}
    with pytest.raises(RpcError):
        get_block_number(rpc.node())

    rpc.responder = lambda request: {"result": {"number": "zzz"}}
    with pytest.raises(RpcError):
        get_block_number(rpc.node())


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0, "0x0"),
        (16, "0x10"),
        ("16", "0x10"),
        ("0x0010", "0x10"),
        ("0x0", "0x0"),
        ("latest", "latest"),
        ("finalized", "finalized"),
    ],
)
def test_to_quantity(value, expected):
    assert to_quantity(value) == expected


@pytest.mark.parametrize("value", [-1, True, "abc", "0xzz", 1.5])
def test_to_quantity_rejects_invalid(value):
    with pytest.raises(ValueError):
        to_quantity(value)
