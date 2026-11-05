import pytest

from micro_web3 import (
    MULTICALL3_ADDRESS,
    AbiError,
    RpcError,
    decode,
    encode,
    try_aggregate,
)
from micro_web3.abi import selector
from micro_web3.multicall import _MULTICALL3_ABI

TARGET = "0x52908400098527886e0f7030069857d2e4169ee7"
OTHER = "0xde709f2102306220921060314715629080e2fb77"


def _aggregate_payload(results):
    return "0x" + encode(["(bool,bytes)[]"], [results]).hex()


def test_try_aggregate_maps_failures_to_none(rpc):
    rpc.responder = lambda request: {
        "result": _aggregate_payload([(True, b"\x01"), (False, b""), (True, b"\x00\x02")]),
    }

    results = try_aggregate(
        rpc.node(),
        [(TARGET, b"\x31\x3c\xe5\x67"), (OTHER, "0x70a08231"), (TARGET, b"")],
    )

    assert results == [b"\x01", None, b"\x00\x02"]


def test_try_aggregate_request_shape(rpc):
    rpc.responder = lambda request: {"result": _aggregate_payload([])}
    try_aggregate(rpc.node(), [(TARGET, b"\x31\x3c\xe5\x67")])

    request = rpc.requests[0]
    assert request["method"] == "eth_call"
    params = request["params"][0]
    assert params["to"] == MULTICALL3_ADDRESS
    assert params["data"][2:10] == selector(_MULTICALL3_ABI[0]).hex()
    require_success, calls = decode(["bool", "(address,bytes)[]"], params["data"][10:])
    assert require_success is False
    assert calls == ((TARGET, b"\x31\x3c\xe5\x67"),)


def test_try_aggregate_empty_calls(rpc):
    rpc.responder = lambda request: {"result": _aggregate_payload([])}
    assert try_aggregate(rpc.node(), []) == []


def test_try_aggregate_propagates_rpc_errors(rpc):
    rpc.responder = lambda request: {"error": {"code": -32000, "message": "boom"}}
    with pytest.raises(RpcError):
        try_aggregate(rpc.node(), [(TARGET, b"")])


def test_try_aggregate_rejects_bad_calldata(rpc):
    with pytest.raises(AbiError):
        try_aggregate(rpc.node(), [(TARGET, "not-hex")])
