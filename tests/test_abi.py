import json
from pathlib import Path

import pytest

from micro_web3 import AbiError, AbiType, canonical, decode, encode, parse_type
from micro_web3.abi import decode_outputs, encode_call, find_function, selector
from micro_web3.multicall import _MULTICALL3_ABI

VECTORS = json.loads((Path(__file__).parent / "vectors.json").read_text())
ADDRESS = "0x52908400098527886e0f7030069857d2e4169ee7"


def untag(value):
    if isinstance(value, dict) and "__bytes__" in value:
        return bytes.fromhex(value["__bytes__"])
    if isinstance(value, list):
        return [untag(item) for item in value]
    return value


def tag(value):
    if isinstance(value, bytes):
        return {"__bytes__": value.hex()}
    if isinstance(value, (list, tuple)):
        return [tag(item) for item in value]
    return value


@pytest.mark.parametrize("vector", VECTORS["vectors"], ids=lambda v: v["types"][0])
def test_encode_matches_eth_abi(vector):
    values = [untag(item) for item in vector["values"]]
    assert encode(vector["types"], values).hex() == vector["encoded"]


@pytest.mark.parametrize("vector", VECTORS["vectors"], ids=lambda v: v["types"][0])
def test_decode_matches_eth_abi(vector):
    decoded = decode(vector["types"], bytes.fromhex(vector["encoded"]))
    assert [tag(item) for item in decoded] == vector["decoded"]


def test_arrays_and_tuples_decode_to_tuples():
    decoded = decode(
        ["uint256[]", "(uint256,address)"],
        encode(
            ["uint256[]", "(uint256,address)"],
            [[1, 2], (3, ADDRESS)],
        ),
    )
    assert isinstance(decoded[0], tuple)
    assert isinstance(decoded[1], tuple)
    assert decoded[0] == (1, 2)


def test_address_hex_string_is_accepted_for_bytes_types():
    assert encode(["bytes2"], ["0xabcd"]) == b"\xab\xcd".ljust(32, b"\x00")


def test_selector_vectors():
    abi = [
        {
            "type": "function",
            "name": "transfer",
            "inputs": [
                {"name": "to", "type": "address"},
                {"name": "amount", "type": "uint256"},
            ],
        },
        {
            "type": "function",
            "name": "balanceOf",
            "inputs": [{"name": "owner", "type": "address"}],
        },
        {
            "type": "function",
            "name": "approve",
            "inputs": [
                {"name": "spender", "type": "address"},
                {"name": "amount", "type": "uint256"},
            ],
        },
    ]
    assert selector(find_function(abi, "transfer", [ADDRESS, 1])).hex() == "a9059cbb"
    assert selector(find_function(abi, "balanceOf", [ADDRESS])).hex() == "70a08231"
    assert selector(find_function(abi, "approve", [ADDRESS, 1])).hex() == "095ea7b3"
    assert selector(_MULTICALL3_ABI[0]).hex() == "bce38bd7"


def test_encode_call_pads_address():
    abi = [
        {
            "type": "function",
            "name": "balanceOf",
            "inputs": [{"name": "owner", "type": "address"}],
            "outputs": [{"name": "", "type": "uint256"}],
        },
    ]
    encoded = encode_call(abi, "balanceOf", [ADDRESS])
    assert encoded == "0x70a08231" + "00" * 12 + ADDRESS[2:]


def test_overload_resolution_prefers_a_working_encoding():
    abi = [
        {"type": "function", "name": "foo", "inputs": [{"name": "a", "type": "uint256"}]},
        {"type": "function", "name": "foo", "inputs": [{"name": "a", "type": "address"}]},
    ]
    assert find_function(abi, "foo", [ADDRESS])["inputs"][0]["type"] == "address"
    assert find_function(abi, "foo", [5])["inputs"][0]["type"] == "uint256"


def test_ambiguous_overload_uses_abi_order():
    abi = [
        {"type": "function", "name": "foo", "inputs": [{"name": "a", "type": "uint256"}]},
        {"type": "function", "name": "foo", "inputs": [{"name": "a", "type": "uint8"}]},
    ]
    assert find_function(abi, "foo", [1])["inputs"][0]["type"] == "uint256"


def test_unknown_name_raises_attribute_error():
    with pytest.raises(AttributeError):
        find_function([], "nope", [])


def test_bad_arguments_raise_abi_error():
    abi = [
        {
            "type": "function",
            "name": "foo",
            "inputs": [{"name": "a", "type": "uint256"}],
        },
    ]
    with pytest.raises(AbiError):
        find_function(abi, "foo", ["not-a-number"])
    with pytest.raises(AbiError):
        find_function(abi, "foo", [1, 2])


def test_decode_outputs_accepts_hex_and_bytes():
    encoded = encode(["uint256"], [7])
    assert decode_outputs(["uint256"], encoded) == (7,)
    assert decode_outputs(["uint256"], "0x" + encoded.hex()) == (7,)


def test_zero_outputs_ignore_empty_payload():
    assert decode_outputs([], "0x") == ()


@pytest.mark.parametrize(
    ("types", "values"),
    [
        (["uint8"], [-1]),
        (["uint8"], [256]),
        (["int8"], [128]),
        (["int8"], [-129]),
        (["uint256"], [True]),
        (["bytes32"], [b"\x00" * 33]),
        (["string"], [b"bytes"]),
        (["uint8[2]"], [[1]]),
        (["address"], ["0x1234"]),
        (["uint7"], [1]),
        (["nope"], [1]),
        (["uint256"], ["1"]),
    ],
)
def test_invalid_values_raise_abi_error(types, values):
    with pytest.raises(AbiError):
        encode(types, values)


def test_truncated_payload_raises_abi_error():
    with pytest.raises(AbiError):
        decode(["uint256"], b"\x00" * 31)
    with pytest.raises(AbiError):
        decode(["bytes"], (5).to_bytes(32, "big"))


def test_absurd_array_length_is_rejected():
    word = (2**256 - 1).to_bytes(32, "big")
    with pytest.raises(AbiError):
        decode(["uint256[]"], word)


def test_invalid_utf8_string_raises_abi_error():
    payload = (1).to_bytes(32, "big") + b"\xff".ljust(32, b"\x00")
    with pytest.raises(AbiError):
        decode(["string"], payload)


def test_type_parsing_and_canonical_form():
    parsed = parse_type("(uint256,(bool,bytes)[])[2]")
    assert isinstance(parsed, AbiType)
    assert canonical(parsed) == "(uint256,(bool,bytes)[])[2]"
    assert canonical(parse_type("function")) == "bytes24"
    assert canonical(parse_type("tuple[]", [{"type": "address"}])) == "(address)[]"


@pytest.mark.parametrize("type_str", ["uint", "int", "bytes33", "uint0", "uint257", "(uint256"])
def test_invalid_type_strings(type_str):
    with pytest.raises(AbiError):
        parse_type(type_str)
