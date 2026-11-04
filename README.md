# micro-web3

A small Ethereum client: JSON-RPC over the standard library, a hand-rolled
Solidity ABI codec, EIP-55 checksums, and Multicall3 batching.

Built to replace the slice of web3.py that a backend actually uses, without
pulling in web3, eth-abi, eth-utils, eth-typing, or their transitive
dependencies. One runtime dependency, `pycryptodome`, for Keccak-256.

- Python 3.13+
- HTTP via `urllib.request`; no requests, no connection pool, no retries
- No ABI/type/hex-byte libraries
- `py.typed`

## Install

```console
uv add micro-web3
```

## Quickstart

```python
from micro_web3 import Contract, RpcNode

node = RpcNode("https://ethereum-rpc.publicnode.com", timeout=4)
node.endpoint_uri  # 'https://ethereum-rpc.publicnode.com'
node.is_connected()  # web3_clientVersion probe; False instead of raising

erc20 = Contract("0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48", abi)
erc20.call(node, "decimals")  # 6
erc20.call(node, "balanceOf", [holder])  # int
erc20.encode("balanceOf", [holder])  # '0x70a08231...' (hex, selector included)
```

`Contract.call` performs one `eth_call` and decodes the result: a single
output is unwrapped, multiple outputs come back as a tuple.

### Logs

```python
from micro_web3 import get_logs

logs = get_logs(node, address=token, topics=[transfer_topic], from_block=0, to_block="latest")
logs[0]["blockNumber"]  # '0x...' — raw JSON-RPC, never normalised
logs[0]["data"]  # '0x...'
```

Raw hex is deliberate: it matches the Etherscan/Blockscout shapes, so one
consumer can handle every indexer identically. Block filters accept `int`,
decimal strings, hex strings or tags; they are emitted as JSON-RPC quantities.

### Multicall

```python
from micro_web3 import try_aggregate

results = try_aggregate(
    node,
    [
        (token_a, erc20.encode("balanceOf", [holder])),
        (token_b, erc20.encode("balanceOf", [holder])),
    ],
)
# [b'...', None] — one entry per call, None where that call reverted
```

`try_aggregate` uses Multicall3's `tryAggregate(false, calls)`.

### ABI

```python
from micro_web3 import decode_outputs, encode_call, to_checksum_address

data = encode_call(abi, "transfer", [to, amount])
values = decode_outputs(["uint256"], "0x" + "00" * 31 + "2a")
```

Supported types: `address`, `bool`, `uintN`, `intN`, `bytesN`, `bytes`,
`string`, `function`, fixed and dynamic arrays, tuples, and nested
combinations (`(bool,bytes)[]`, `uint256[2][]`, ...).

Decoding matches eth_abi 6: addresses are lower-case hex strings, arrays and
tuples are tuples, `bytesN` is `bytes`. Use `to_checksum_address` when you need
EIP-55 form.

## Errors

Every failure derives from `RpcError`:

| Class | Raised for |
|---|---|
| `RpcConnectionError` | unreachable node, timeout, non-JSON HTTP response |
| `RpcResponseError` | JSON-RPC `error` object; `.code`, `.message`, `.data` |
| `AbiError` | unknown type, bad value, undecodable payload |

Reverts arrive as `RpcResponseError` with `execution reverted` in the message
and the revert payload in `.data`. Looking up a function that the ABI does not
contain raises `AttributeError`, which callers can use to fall back to another
indexer.

## What replaces what

| web3.py | micro-web3 |
|---|---|
| `Web3(Web3.HTTPProvider(uri, request_kwargs={'timeout': 4}))` | `RpcNode(uri, timeout=4)` |
| `node.is_connected()` | `node.is_connected()` |
| `web3.manager.request_blocking(method, params)` | `node.request(method, params)` |
| `contract.encode_abi(name, args=)` | `contract.encode(name, args)` |
| `contract._find_matching_fn_abi(name, *args)` | `contract.function(name, args)` |
| `contract.caller().fn(*args)` | `contract.call(node, name, args)` |
| `web3.codec.decode(types, data)` | `decode_outputs(types, data)` |
| `node.eth.get_logs(options)` | `get_logs(node, ...)` |
| `node.eth.get_block('latest')['number']` | `get_block_number(node)` |
| `Web3.to_checksum_address` | `to_checksum_address` |
| `web3.exceptions.Web3Exception` | `RpcError` |

## Development

```console
uv sync --all-groups
uv run pytest
MICRON_RPC_URL=https://ethereum-rpc.publicnode.com uv run pytest tests/test_live.py
uv run ruff check .
uv run ruff format --check .
uv run pyrefly check
```

The ABI tests run against vectors generated with eth_abi 6 (`tests/vectors.json`),
so the hand-rolled codec is checked against the reference implementation
without depending on it.
