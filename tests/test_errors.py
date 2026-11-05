"""Every failure the library raises is a :class:`MicroWeb3Error`.

Input-validation errors also derive from the builtin that fits the failure
(``ValueError``, ``TypeError``, ``AttributeError``, ``UnicodeEncodeError``);
the builtin follows the error, not the call site.
"""

import copy
import pickle

import pytest

from micro_web3 import (
    AbiError,
    AbiType,
    AddressError,
    BlockNumberError,
    CalldataError,
    Contract,
    ContractError,
    FunctionNotFoundError,
    ImmutableAbiTypeError,
    MessageEncodingError,
    MessageTypeError,
    MicroWeb3Error,
    RpcConnectionError,
    RpcError,
    RpcNode,
    RpcResponseError,
    SignatureError,
    SignatureTypeError,
    eth_call,
    find_function,
    personal_sign_hash,
    recover_message_address,
    to_checksum_address,
    to_quantity,
)

ADDRESS = "0x52908400098527886e0f7030069857d2e4169ee7"


def test_response_error(rpc):
    rpc.responder = lambda request: {"error": {"code": 3, "message": "boom"}}
    with pytest.raises(RpcResponseError) as excinfo:
        rpc.node().request("eth_call", [{}])
    assert isinstance(excinfo.value, MicroWeb3Error)


def test_connection_error():
    node = RpcNode("http://127.0.0.1:1", timeout=0.2)
    with pytest.raises(RpcConnectionError) as excinfo:
        node.request("eth_blockNumber")
    assert isinstance(excinfo.value, MicroWeb3Error)


def test_abi_error():
    abi = [{"type": "function", "name": "f", "inputs": [{"type": "uint8"}]}]
    with pytest.raises(AbiError) as excinfo:
        find_function(abi, "f", [256])
    assert isinstance(excinfo.value, MicroWeb3Error)
    assert not isinstance(excinfo.value, RpcError)


@pytest.mark.parametrize("abi", [None, "not a list", {"name": "f"}, [1]])
def test_malformed_abi_is_an_abi_error(abi):
    with pytest.raises(AbiError) as excinfo:
        find_function(abi, "f")  # type: ignore[arg-type]
    assert isinstance(excinfo.value, MicroWeb3Error)
    assert not isinstance(excinfo.value, RpcError)

    with pytest.raises(AbiError) as excinfo:
        Contract(ADDRESS, abi)  # type: ignore[arg-type]
    assert isinstance(excinfo.value, MicroWeb3Error)


def test_signature_error():
    with pytest.raises(SignatureError) as excinfo:
        recover_message_address("hello", "0x1234")
    assert isinstance(excinfo.value, MicroWeb3Error)
    assert not isinstance(excinfo.value, RpcError)


@pytest.mark.parametrize("value", ["0x1234", 42, None])
def test_address_error(value):
    with pytest.raises(AddressError) as excinfo:
        to_checksum_address(value)  # type: ignore[arg-type]
    assert isinstance(excinfo.value, MicroWeb3Error)
    assert isinstance(excinfo.value, ValueError)


@pytest.mark.parametrize("value", [-1, True, "abc", "0xzz", 1.5, "²", "9" * 5000])
def test_block_number_error(value):
    with pytest.raises(BlockNumberError) as excinfo:
        to_quantity(value)
    assert isinstance(excinfo.value, MicroWeb3Error)
    assert isinstance(excinfo.value, ValueError)


def test_calldata_error():
    with pytest.raises(CalldataError) as excinfo:
        eth_call(RpcNode("http://127.0.0.1:1"), ADDRESS, 42)  # type: ignore[arg-type]
    assert isinstance(excinfo.value, MicroWeb3Error)
    assert isinstance(excinfo.value, ValueError)


def test_contract_error():
    contract = Contract(None, [])
    with pytest.raises(ContractError) as excinfo:
        contract.call(RpcNode("http://127.0.0.1:1"), "f")
    assert isinstance(excinfo.value, MicroWeb3Error)
    assert isinstance(excinfo.value, ValueError)


def test_function_not_found_error():
    with pytest.raises(FunctionNotFoundError) as excinfo:
        find_function([], "nope")
    assert isinstance(excinfo.value, MicroWeb3Error)
    assert isinstance(excinfo.value, AttributeError)

    with pytest.raises(FunctionNotFoundError) as excinfo:
        Contract(ADDRESS, []).encode("nope")
    assert isinstance(excinfo.value, MicroWeb3Error)
    assert isinstance(excinfo.value, AttributeError)


def test_immutable_abi_type_error():
    abi_type = AbiType(kind="uint")
    with pytest.raises(ImmutableAbiTypeError) as excinfo:
        abi_type.kind = "int"  # type: ignore[misc]
    assert isinstance(excinfo.value, MicroWeb3Error)
    assert isinstance(excinfo.value, AttributeError)

    with pytest.raises(ImmutableAbiTypeError) as excinfo:
        del abi_type.fields  # type: ignore[misc]
    assert isinstance(excinfo.value, MicroWeb3Error)
    assert isinstance(excinfo.value, AttributeError)


@pytest.mark.parametrize("value", [5, 1.5, None, ["x"]])
def test_message_type_error(value):
    with pytest.raises(MessageTypeError) as excinfo:
        personal_sign_hash(value)  # type: ignore[arg-type]
    assert isinstance(excinfo.value, MicroWeb3Error)
    assert isinstance(excinfo.value, TypeError)


def test_signature_type_error():
    with pytest.raises(SignatureTypeError) as excinfo:
        recover_message_address("hello", 123)  # type: ignore[arg-type]
    assert isinstance(excinfo.value, MicroWeb3Error)
    assert isinstance(excinfo.value, TypeError)


def test_message_encoding_error():
    with pytest.raises(MessageEncodingError) as excinfo:
        personal_sign_hash("\ud800")
    assert isinstance(excinfo.value, MicroWeb3Error)
    assert isinstance(excinfo.value, UnicodeEncodeError)

    with pytest.raises(MessageEncodingError) as excinfo:
        recover_message_address(
            "\ud800",
            "2a73ec42acd33331635dcab78139d763b36ba303fc64940acd5f6797f83a78e1"
            "6cf49ce6937869cf5144c10c3bcfc07d25a3155cd96315176775c812f700173a1c",
        )
    assert isinstance(excinfo.value, MicroWeb3Error)
    assert isinstance(excinfo.value, UnicodeEncodeError)


def test_message_encoding_error_survives_pickle_and_copy():
    with pytest.raises(MessageEncodingError) as excinfo:
        personal_sign_hash("\ud800")
    error = excinfo.value

    restored = pickle.loads(pickle.dumps(error))
    assert isinstance(restored, MessageEncodingError)
    assert restored.args == error.args == ("utf-8", error.object, 0, 1, error.reason)

    assert copy.copy(error).args == error.args
