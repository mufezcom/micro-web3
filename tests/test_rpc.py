import pytest

from micro_web3 import (
    RpcConnectionError,
    RpcError,
    RpcResponseError,
    to_checksum_address,
)

ADDRESS = "0x52908400098527886e0f7030069857d2e4169ee7"


def test_request_round_trip(rpc):
    rpc.responder = lambda request: {"result": "0xabc"}
    node = rpc.node()

    assert node.request("eth_blockNumber") == "0xabc"
    sent = rpc.requests[0]
    assert sent["jsonrpc"] == "2.0"
    assert sent["method"] == "eth_blockNumber"
    assert sent["params"] == []
    assert sent["id"] == 1
    assert node.endpoint_uri == rpc.url


def test_params_are_passed_through(rpc):
    rpc.responder = lambda request: {"result": "ok"}
    node = rpc.node()

    node.request("eth_getBlockByNumber", ["latest", False])
    assert rpc.requests[0]["params"] == ["latest", False]

    node.request("eth_getLogs", {"fromBlock": "0x1"})
    assert rpc.requests[1]["params"] == [{"fromBlock": "0x1"}]


def test_json_rpc_error_raises_response_error(rpc):
    rpc.responder = lambda request: {
        "error": {
            "code": 3,
            "message": "execution reverted: nope",
            "data": "0x08c379a0",
        },
    }
    with pytest.raises(RpcResponseError) as excinfo:
        rpc.node().request("eth_call", [{}])

    assert excinfo.value.code == 3
    assert "execution reverted" in str(excinfo.value)
    assert excinfo.value.data == "0x08c379a0"
    assert isinstance(excinfo.value, RpcError)


def test_http_error_with_json_body_surfaces_rpc_error(rpc):
    rpc.status = 400
    rpc.raw_body = b'{"jsonrpc":"2.0","id":1,"error":{"code":-32600,"message":"bad"}}'
    with pytest.raises(RpcResponseError) as excinfo:
        rpc.node().request("eth_call", [{}])
    assert excinfo.value.code == -32600


def test_http_error_without_json_body_raises_connection_error(rpc):
    rpc.status = 502
    rpc.raw_body = b"<html>bad gateway</html>"
    with pytest.raises(RpcConnectionError) as excinfo:
        rpc.node().request("eth_blockNumber")
    assert excinfo.value.status == 502
    assert "bad gateway" in str(excinfo.value)


def test_invalid_json_raises_rpc_error(rpc):
    rpc.raw_body = b"not json"
    with pytest.raises(RpcError):
        rpc.node().request("eth_blockNumber")


def test_missing_result_raises_rpc_error(rpc):
    rpc.responder = lambda request: {"error": None}
    with pytest.raises(RpcError):
        rpc.node().request("eth_blockNumber")


def test_unreachable_node_raises_connection_error():
    node = __import__("micro_web3").RpcNode("http://127.0.0.1:1", timeout=0.2)
    with pytest.raises(RpcConnectionError):
        node.request("eth_blockNumber")


def test_timeout_raises_connection_error(rpc):
    rpc.delay = 0.5
    rpc.responder = lambda request: {"result": "0x1"}
    with pytest.raises(RpcConnectionError):
        rpc.node(timeout=0.05).request("eth_blockNumber")


def test_is_connected_true(rpc):
    rpc.responder = lambda request: {"result": "Geth/v1.14.0"}
    assert rpc.node().is_connected() is True


def test_is_connected_false_on_empty_version(rpc):
    rpc.responder = lambda request: {"result": ""}
    assert rpc.node().is_connected() is False


def test_is_connected_false_on_rpc_error(rpc):
    rpc.responder = lambda request: {"error": {"code": -32601, "message": "nope"}}
    assert rpc.node().is_connected() is False


def test_is_connected_false_when_unreachable():
    node = __import__("micro_web3").RpcNode("http://127.0.0.1:1", timeout=0.2)
    assert node.is_connected() is False


def test_endpoint_uri_is_exposed(rpc):
    node = rpc.node()
    assert node.endpoint_uri.startswith("http://127.0.0.1:")
    assert to_checksum_address(ADDRESS) == "0x52908400098527886E0F7030069857D2E4169EE7"
