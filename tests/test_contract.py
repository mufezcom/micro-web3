import pytest

from micro_web3 import AbiError, Contract
from micro_web3.abi import encode

ADDRESS = "0x52908400098527886e0f7030069857d2e4169ee7"
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
        "name": "balanceOf",
        "stateMutability": "view",
        "inputs": [{"name": "owner", "type": "address"}],
        "outputs": [{"name": "", "type": "uint256"}],
    },
    {
        "type": "function",
        "name": "getReserves",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [
            {"name": "reserve0", "type": "uint112"},
            {"name": "reserve1", "type": "uint112"},
            {"name": "blockTimestampLast", "type": "uint32"},
        ],
    },
    {
        "type": "function",
        "name": "transfer",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "to", "type": "address"},
            {"name": "amount", "type": "uint256"},
        ],
        "outputs": [{"name": "", "type": "bool"}],
    },
]


def test_address_is_checksummed():
    contract = Contract(ADDRESS, ERC20_ABI)
    assert contract.address == "0x52908400098527886E0F7030069857D2E4169EE7"


def test_encode_matches_known_calldata():
    contract = Contract(ADDRESS, ERC20_ABI)
    assert contract.encode("balanceOf", [ADDRESS]) == ("0x70a08231" + "00" * 12 + ADDRESS[2:])
    assert contract.encode("transfer", [ADDRESS, 10]).startswith("0xa9059cbb")


def test_call_unwraps_single_output(rpc):
    rpc.responder = lambda request: {"result": "0x" + (18).to_bytes(32, "big").hex()}
    contract = Contract(ADDRESS, ERC20_ABI)

    assert contract.call(rpc.node(), "decimals") == 18
    params = rpc.requests[0]["params"]
    assert params[0]["data"] == contract.encode("decimals")
    assert params[1] == "latest"


def test_call_returns_tuple_for_multiple_outputs(rpc):
    payload = encode(["uint112", "uint112", "uint32"], [1, 2, 3])
    rpc.responder = lambda request: {"result": "0x" + payload.hex()}

    assert Contract(ADDRESS, ERC20_ABI).call(rpc.node(), "getReserves") == (1, 2, 3)


def test_call_with_no_outputs_returns_empty_tuple(rpc):
    rpc.responder = lambda request: {"result": "0x"}
    abi = [
        {
            "type": "function",
            "name": "poke",
            "inputs": [],
            "outputs": [],
        },
    ]
    assert Contract(ADDRESS, abi).call(rpc.node(), "poke") == ()


def test_decoded_addresses_are_lowercase(rpc):
    abi = [
        {
            "type": "function",
            "name": "owner",
            "inputs": [],
            "outputs": [{"name": "", "type": "address"}],
        },
    ]
    payload = encode(["address"], [ADDRESS])
    rpc.responder = lambda request: {"result": "0x" + payload.hex()}

    assert Contract(ADDRESS, abi).call(rpc.node(), "owner") == ADDRESS.lower()


def test_call_requires_address():
    with pytest.raises(ValueError):
        Contract(None, ERC20_ABI).call(__import__("micro_web3").RpcNode("http://x"), "decimals")


def test_unknown_function_raises_attribute_error():
    with pytest.raises(AttributeError):
        Contract(ADDRESS, ERC20_ABI).encode("nope")


def test_bad_arguments_raise_abi_error():
    with pytest.raises(AbiError):
        Contract(ADDRESS, ERC20_ABI).encode("balanceOf", [])


def test_undecodable_payload_raises_abi_error(rpc):
    rpc.responder = lambda request: {"result": "0x"}
    with pytest.raises(AbiError):
        Contract(ADDRESS, ERC20_ABI).call(rpc.node(), "decimals")


def test_output_types_are_canonical():
    contract = Contract(ADDRESS, ERC20_ABI)
    assert contract.output_types("decimals") == ("uint8",)
    assert contract.output_types("getReserves") == ("uint112", "uint112", "uint32")


def test_repr():
    assert repr(Contract(ADDRESS, ERC20_ABI)) == (
        "Contract(address='0x52908400098527886E0F7030069857D2E4169EE7', functions=4)"
    )


def test_reassigning_abi_drops_cached_functions():
    def entry(type_):
        return {"type": "function", "name": "f", "inputs": [{"type": type_}], "outputs": []}

    contract = Contract(None, [entry("uint256")])
    before = contract.encode("f", [1])
    contract.abi = [entry("uint8")]
    assert contract.encode("f", [1]) != before
