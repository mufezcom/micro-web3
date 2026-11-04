"""A tiny contract helper on top of the ABI codec."""

from collections.abc import Mapping, Sequence
from typing import Any

from .abi import (
    AbiType,
    canonical,
    decode_outputs,
    encode_call,
    find_function,
    outputs_types,
)
from .addresses import to_checksum_address
from .methods import eth_call
from .rpc import RpcNode

__all__ = ["Contract"]


class Contract:
    """An ABI plus (optionally) an address.

    ``Contract.encode`` returns ``0x`` hex like web3's ``encode_abi``, so the
    Etherscan fallback path keeps working unchanged.
    """

    __slots__ = ("abi", "address")

    def __init__(
        self,
        address: str | bytes | None,
        abi: Sequence[Mapping[str, Any]],
    ) -> None:
        self.address = None if address is None else to_checksum_address(address)
        self.abi = tuple(abi)

    def function(self, name: str, args: Sequence[Any] = ()) -> Mapping[str, Any]:
        """Return the matching ABI entry.

        Raises :class:`AttributeError` if no function has that name and
        :class:`~micro_web3.errors.AbiError` if the arguments do not fit any
        overload.
        """
        return find_function(self.abi, name, args)

    def encode(self, name: str, args: Sequence[Any] = ()) -> str:
        """Encode a call, ``0x`` hex including the 4-byte selector."""
        return encode_call(self.abi, name, args)

    def output_types(self, name: str, args: Sequence[Any] = ()) -> tuple[str, ...]:
        return tuple(canonical(item) for item in self._outputs(name, args))

    def decode(self, name: str, args: Sequence[Any], data: str | bytes) -> Any:
        """Decode a return payload, unwrapping single-output results."""
        outputs = self._outputs(name, args)
        decoded = decode_outputs(outputs, data)
        if len(decoded) == 1:
            return decoded[0]
        return decoded

    def call(
        self,
        node: RpcNode,
        name: str,
        args: Sequence[Any] = (),
        block: int | str = "latest",
    ) -> Any:
        """``eth_call`` the function and decode the result."""
        if self.address is None:
            raise ValueError("contract has no address; cannot perform a call")
        raw = eth_call(node, self.address, self.encode(name, args), block)
        return self.decode(name, args, raw)

    def _outputs(self, name: str, args: Sequence[Any]) -> tuple[AbiType, ...]:
        return outputs_types(self.function(name, args))

    def __repr__(self) -> str:
        functions = sum(1 for entry in self.abi if entry.get("type", "function") == "function")
        return f"Contract(address={self.address!r}, functions={functions})"
