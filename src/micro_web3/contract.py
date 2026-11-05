"""A tiny contract helper on top of the ABI codec."""

from collections.abc import Mapping, Sequence
from functools import cached_property
from typing import Any

from .abi import (
    AbiType,
    canonical,
    decode_outputs,
    encode,
    inputs_types,
    outputs_types,
    selector,
)
from .addresses import to_checksum_address
from .errors import AbiError, ContractError, FunctionNotFoundError
from .methods import eth_call
from .rpc import RpcNode

__all__ = ["Contract"]


def _unwrap(decoded: tuple[Any, ...]) -> Any:
    return decoded[0] if len(decoded) == 1 else decoded


class _Function:
    """One ABI entry with its types and selector, derived on first use."""

    def __init__(self, entry: Mapping[str, Any]) -> None:
        self.entry = entry

    @cached_property
    def inputs(self) -> tuple[AbiType, ...]:
        return inputs_types(self.entry)

    @cached_property
    def outputs(self) -> tuple[AbiType, ...]:
        return outputs_types(self.entry)

    @cached_property
    def selector(self) -> bytes:
        return selector(self.entry)


class Contract:
    """An ABI plus (optionally) an address.

    ``Contract.encode`` returns ``0x`` hex like web3's ``encode_abi``, so the
    Etherscan fallback path keeps working unchanged.
    """

    __slots__ = ("_abi", "_functions", "address")

    def __init__(
        self,
        address: str | bytes | None,
        abi: Sequence[Mapping[str, Any]],
    ) -> None:
        self.address = None if address is None else to_checksum_address(address)
        self.abi = abi

    @property
    def abi(self) -> tuple[Mapping[str, Any], ...]:
        return self._abi

    @abi.setter
    def abi(self, abi: Sequence[Mapping[str, Any]]) -> None:
        self._abi = tuple(abi)
        self._functions: dict[str, tuple[_Function, ...]] = {}

    def function(self, name: str, args: Sequence[Any] = ()) -> Mapping[str, Any]:
        """Return the matching ABI entry.

        Raises :class:`~micro_web3.errors.FunctionNotFoundError` (an
        ``AttributeError``) if no function has that name and
        :class:`~micro_web3.errors.AbiError` if the arguments do not fit any
        overload.
        """
        return self._resolve(name, args)[0].entry

    def encode(self, name: str, args: Sequence[Any] = ()) -> str:
        """Encode a call, ``0x`` hex including the 4-byte selector."""
        function, body = self._resolve(name, args)
        return "0x" + (function.selector + body).hex()

    def output_types(self, name: str, args: Sequence[Any] = ()) -> tuple[str, ...]:
        return tuple(canonical(item) for item in self._outputs(name, args))

    def decode(self, name: str, args: Sequence[Any], data: str | bytes) -> Any:
        """Decode a return payload, unwrapping single-output results."""
        return _unwrap(decode_outputs(self._outputs(name, args), data))

    def call(
        self,
        node: RpcNode,
        name: str,
        args: Sequence[Any] = (),
        block: int | str = "latest",
    ) -> Any:
        """``eth_call`` the function and decode the result."""
        if self.address is None:
            raise ContractError("contract has no address; cannot perform a call")
        function, body = self._resolve(name, args)
        raw = eth_call(node, self.address, "0x" + (function.selector + body).hex(), block)
        return _unwrap(decode_outputs(function.outputs, raw))

    def _outputs(self, name: str, args: Sequence[Any]) -> tuple[AbiType, ...]:
        return self._resolve(name, args)[0].outputs

    def _resolve(self, name: str, args: Sequence[Any]) -> tuple[_Function, bytes]:
        """First overload accepting ``args``, with the encoded arguments."""
        functions = self._functions.get(name)
        if functions is None:
            functions = tuple(
                _Function(entry)
                for entry in self.abi
                if entry.get("type", "function") == "function" and entry.get("name") == name
            )
            if not functions:
                raise FunctionNotFoundError(f"ABI has no function named {name!r}")
            self._functions[name] = functions
        failures: list[str] = []
        for function in functions:
            try:
                return function, encode(function.inputs, args)
            except AbiError as exc:
                failures.append(str(exc))
        raise AbiError(
            f"no overload of {name!r} accepts {len(args)} argument(s): " + "; ".join(failures),
        )

    def __repr__(self) -> str:
        functions = sum(1 for entry in self.abi if entry.get("type", "function") == "function")
        return f"Contract(address={self.address!r}, functions={functions})"
