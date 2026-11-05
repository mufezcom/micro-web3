"""Hand-rolled Solidity ABI codec.

Covers every type that appears in practice: ``address``, ``bool``, ``uintN``,
``intN``, ``bytesN``, ``bytes``, ``string``, static/dynamic arrays and tuples
(including nested ``tuple[]``). Semantics mirror ``eth_abi`` 6: decoded arrays
and tuples are tuples, addresses are lower-case ``0x`` hex, ``bytesN`` is
``bytes``.
"""

from collections.abc import Mapping, Sequence
from functools import lru_cache
from typing import Any

from ._keccak import keccak256
from .addresses import to_bytes20
from .errors import AbiError

_WORD = 1 << 256


_STATIC_KINDS = frozenset({"uint", "int", "address", "bool", "fixedbytes"})


class AbiType:
    """A parsed ABI type. ``kind`` is one of uint, int, address, bool,
    fixedbytes, bytes, string, array, tuple.

    Immutable. ``dynamic`` and ``head_size`` are derived once here so the codec
    does not recurse per value; ``head_size`` is ``None`` for a malformed type.
    """

    __slots__ = ("bits", "dynamic", "elem", "fields", "head_size", "kind", "length", "size")
    __match_args__ = ("kind", "bits", "size", "length", "elem", "fields")

    kind: str
    bits: int
    size: int
    length: "int | None"
    elem: "AbiType | None"
    fields: "tuple[AbiType, ...]"
    dynamic: bool
    head_size: "int | None"

    def __init__(
        self,
        kind: str,
        bits: int = 0,
        size: int = 0,
        length: "int | None" = None,
        elem: "AbiType | None" = None,
        fields: "tuple[AbiType, ...]" = (),
    ) -> None:
        dynamic = False
        head_size: int | None = None
        if kind in _STATIC_KINDS:
            head_size = 32
        elif kind in ("bytes", "string"):
            dynamic, head_size = True, 32
        elif kind == "array":
            if length is None:
                dynamic, head_size = True, 32
            elif elem is not None:
                dynamic = elem.dynamic
                if dynamic:
                    head_size = 32
                elif elem.head_size is not None:
                    head_size = length * elem.head_size
        elif kind == "tuple":
            dynamic = any(field.dynamic for field in fields)
            if dynamic:
                head_size = 32
            elif all(field.head_size is not None for field in fields):
                head_size = sum(field.head_size or 0 for field in fields)
        put = object.__setattr__
        put(self, "kind", kind)
        put(self, "bits", bits)
        put(self, "size", size)
        put(self, "length", length)
        put(self, "elem", elem)
        put(self, "fields", fields)
        put(self, "dynamic", dynamic)
        put(self, "head_size", head_size)

    def _key(self) -> tuple[Any, ...]:
        return (self.kind, self.bits, self.size, self.length, self.elem, self.fields)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, AbiType):
            return NotImplemented
        return self._key() == other._key()

    def __hash__(self) -> int:
        return hash(self._key())

    def __repr__(self) -> str:
        return (
            f"AbiType(kind={self.kind!r}, bits={self.bits!r}, size={self.size!r}, "
            f"length={self.length!r}, elem={self.elem!r}, fields={self.fields!r})"
        )

    def __setattr__(self, name: str, value: Any) -> None:
        raise AttributeError(f"cannot assign to field {name!r}")

    def __delattr__(self, name: str) -> None:
        raise AttributeError(f"cannot delete field {name!r}")

    def __reduce__(self) -> tuple[Any, ...]:
        return (AbiType, self._key())


def parse_type(type_str: str, components: Sequence[Mapping[str, Any]] = ()) -> AbiType:
    """Parse a canonical ABI type such as ``(uint256,address)[]``."""
    if components:
        return _parse_type(type_str, components)
    return _parse_string(type_str)


@lru_cache(maxsize=1024)
def _parse_string(type_str: str) -> AbiType:
    return _parse_type(type_str, ())


def _parse_type(type_str: str, components: Sequence[Mapping[str, Any]]) -> AbiType:
    base, dims = _split_dimensions(type_str)
    if base.startswith("("):
        inner = base[1:-1]
        parts = _split_top_level(inner) if inner.strip() else []
        parsed = AbiType(kind="tuple", fields=tuple(parse_type(part) for part in parts))
    elif base == "tuple":
        if not components:
            raise AbiError("tuple type requires components")
        parsed = AbiType(
            kind="tuple",
            fields=tuple(
                parse_type(component.get("type", ""), component.get("components", ()))
                for component in components
            ),
        )
    else:
        parsed = _simple_type(base)

    for length in dims:
        parsed = AbiType(kind="array", elem=parsed, length=length)
    return parsed


def type_from_abi(entry: Mapping[str, Any]) -> AbiType:
    type_str = entry.get("type")
    if not isinstance(type_str, str):
        raise AbiError(f"ABI entry without a string type: {entry!r}")
    return parse_type(type_str, entry.get("components", ()) or ())


def canonical(abi_type: AbiType) -> str:
    kind = abi_type.kind
    if kind in ("uint", "int"):
        return f"{kind}{abi_type.bits}"
    if kind == "fixedbytes":
        return f"bytes{abi_type.size}"
    if kind in ("address", "bool", "bytes", "string"):
        return kind
    if kind == "array":
        if abi_type.elem is None:
            raise AbiError("array type without element type")
        suffix = "[]" if abi_type.length is None else f"[{abi_type.length}]"
        return f"{canonical(abi_type.elem)}{suffix}"
    if kind == "tuple":
        return f"({','.join(canonical(field) for field in abi_type.fields)})"
    raise AbiError(f"unknown ABI type kind {kind!r}")


def is_dynamic(abi_type: AbiType) -> bool:
    kind = abi_type.kind
    if kind in ("bytes", "string"):
        return True
    if kind == "array":
        if abi_type.length is None:
            return True
        if abi_type.elem is None:
            raise AbiError("array type without element type")
        return is_dynamic(abi_type.elem)
    if kind == "tuple":
        return any(is_dynamic(field) for field in abi_type.fields)
    return False


def static_size(abi_type: AbiType) -> int:
    kind = abi_type.kind
    if kind in ("uint", "int", "address", "bool", "fixedbytes"):
        return 32
    if kind in ("bytes", "string"):
        raise AbiError(f"{kind} is dynamic and has no static size")
    if kind == "array":
        if abi_type.elem is None or abi_type.length is None:
            raise AbiError("dynamic array has no static size")
        return abi_type.length * static_size(abi_type.elem)
    if kind == "tuple":
        return sum(static_size(field) for field in abi_type.fields)
    raise AbiError(f"unknown ABI type kind {kind!r}")


# --- encoding -----------------------------------------------------------------


def encode(types: Sequence[str | AbiType], values: Sequence[Any]) -> bytes:
    """Encode ``values`` according to ``types`` (no selector)."""
    parsed = [_coerce_type(item) for item in types]
    return _encode_sequence(parsed, values)


def encode_call(
    abi: Sequence[Mapping[str, Any]],
    name: str,
    args: Sequence[Any] = (),
) -> str:
    """Encode a contract call, returning ``0x`` hex including the selector."""
    function, body = _resolve(abi, name, args)
    return "0x" + (selector(function) + body).hex()


def _encode_sequence(types: Sequence[AbiType], values: Sequence[Any]) -> bytes:
    if len(types) != len(values):
        raise AbiError(f"expected {len(types)} value(s), got {len(values)}")
    try:
        head_size = sum([item.head_size for item in types])  # type: ignore[misc]
    except TypeError:
        for item in types:
            if not is_dynamic(item):
                static_size(item)  # raises the specific error for a malformed type
        raise AbiError(f"malformed ABI type in {types!r}") from None
    heads: list[bytes] = []
    tails: list[bytes] = []
    tail_size = 0
    for abi_type, value in zip(types, values, strict=True):
        if abi_type.dynamic:
            heads.append(_to_word(head_size + tail_size))
            tail = _encode_value(abi_type, value)
            tails.append(tail)
            tail_size += len(tail)
        else:
            heads.append(_encode_value(abi_type, value))
    return b"".join(heads) + b"".join(tails)


def _encode_value(abi_type: AbiType, value: Any) -> bytes:
    kind = abi_type.kind
    if kind == "uint":
        number = _as_int(value, "uint")
        if not 0 <= number < (1 << abi_type.bits):
            raise AbiError(f"{number} out of range for uint{abi_type.bits}")
        return _to_word(number)
    if kind == "int":
        number = _as_int(value, "int")
        bound = 1 << (abi_type.bits - 1)
        if not -bound <= number < bound:
            raise AbiError(f"{number} out of range for int{abi_type.bits}")
        return _to_word(number % _WORD)
    if kind == "bool":
        if not isinstance(value, bool):
            raise AbiError(f"expected bool, got {type(value).__name__}")
        return _to_word(int(value))
    if kind == "address":
        try:
            raw = to_bytes20(value)
        except (TypeError, ValueError) as exc:
            raise AbiError(str(exc)) from exc
        return b"\x00" * 12 + raw
    if kind == "fixedbytes":
        raw = _as_bytes(value)
        if len(raw) > abi_type.size:
            raise AbiError(f"{len(raw)} bytes do not fit in bytes{abi_type.size}")
        return raw.ljust(32, b"\x00")
    if kind == "bytes":
        raw = _as_bytes(value)
        return _to_word(len(raw)) + raw.ljust(_ceil32(len(raw)), b"\x00")
    if kind == "string":
        if not isinstance(value, str):
            raise AbiError(f"expected str, got {type(value).__name__}")
        raw = value.encode("utf-8")
        return _to_word(len(raw)) + raw.ljust(_ceil32(len(raw)), b"\x00")
    if kind == "array":
        if abi_type.elem is None:
            raise AbiError("array type without element type")
        items = _as_sequence(value, "array")
        if abi_type.length is not None and len(items) != abi_type.length:
            raise AbiError(
                f"expected {abi_type.length} array element(s), got {len(items)}",
            )
        elem = abi_type.elem
        if elem.dynamic:
            body = _encode_dynamic_elements(elem, items)
        else:
            body = b"".join([_encode_value(elem, item) for item in items])
        if abi_type.length is None:
            return _to_word(len(items)) + body
        return body
    if kind == "tuple":
        items = _as_sequence(value, "tuple")
        return _encode_sequence(abi_type.fields, items)
    raise AbiError(f"unknown ABI type kind {kind!r}")


def _encode_dynamic_elements(elem: AbiType, items: Sequence[Any]) -> bytes:
    offset = 32 * len(items)
    heads: list[bytes] = []
    tails: list[bytes] = []
    for item in items:
        tail = _encode_value(elem, item)
        heads.append(offset.to_bytes(32, "big"))
        tails.append(tail)
        offset += len(tail)
    return b"".join(heads) + b"".join(tails)


# --- decoding -----------------------------------------------------------------


def decode(types: Sequence[str | AbiType], data: bytes | bytearray | str) -> tuple[Any, ...]:
    """Decode ``data`` into a tuple of Python values."""
    parsed = [_coerce_type(item) for item in types]
    raw = _as_bytes(data)
    if not parsed:
        return ()
    if not raw:
        raise AbiError("cannot decode empty payload")
    values, _ = _decode_sequence(parsed, raw, 0)
    return values


def decode_outputs(
    types: Sequence[str | AbiType],
    data: bytes | bytearray | str,
) -> tuple[Any, ...]:
    """Alias of :func:`decode`, named after the web3/eth_abi helper it replaces."""
    return decode(types, data)


def _decode_sequence(
    types: Sequence[AbiType],
    data: bytes,
    start: int,
) -> tuple[tuple[Any, ...], int]:
    values: list[Any] = []
    position = start
    for abi_type in types:
        if abi_type.dynamic:
            offset = _read_word(data, position)
            value, _ = _decode_value(abi_type, data, start + offset)
            values.append(value)
            position += 32
        else:
            value, position = _decode_value(abi_type, data, position)
            values.append(value)
    return tuple(values), position


def _decode_value(abi_type: AbiType, data: bytes, position: int) -> tuple[Any, int]:
    kind = abi_type.kind
    if kind == "uint":
        return _read_word(data, position), position + 32
    if kind == "int":
        word = _read_word(data, position)
        if word >= 1 << 255:
            word -= _WORD
        return word, position + 32
    if kind == "bool":
        return _read_word(data, position) != 0, position + 32
    if kind == "address":
        _require(data, position, 32)
        return "0x" + data[position + 12 : position + 32].hex(), position + 32
    if kind == "fixedbytes":
        _require(data, position, 32)
        return data[position : position + abi_type.size], position + 32
    if kind in ("bytes", "string"):
        length = _read_word(data, position)
        payload_start = position + 32
        payload_end = payload_start + length
        _require(data, payload_start, length)
        payload = data[payload_start:payload_end]
        end = payload_start + _ceil32(length)
        if kind == "string":
            try:
                return payload.decode("utf-8"), end
            except UnicodeDecodeError as exc:
                raise AbiError("string payload is not valid utf-8") from exc
        return payload, end
    if kind == "array":
        if abi_type.elem is None:
            raise AbiError("array type without element type")
        if abi_type.length is None:
            count = _read_word(data, position)
            elements_start = position + 32
        else:
            count = abi_type.length
            elements_start = position
        if count > (len(data) - elements_start) // 32:
            raise AbiError(f"array of {count} element(s) does not fit in payload")
        return _decode_elements(abi_type.elem, count, data, elements_start)
    if kind == "tuple":
        return _decode_sequence(abi_type.fields, data, position)
    raise AbiError(f"unknown ABI type kind {kind!r}")


def _decode_elements(
    elem: AbiType,
    count: int,
    data: bytes,
    start: int,
) -> tuple[tuple[Any, ...], int]:
    # The caller has checked that ``count`` words fit, so word slices are in bounds.
    if elem.kind == "uint":
        end = start + count * 32
        return tuple([int.from_bytes(data[i : i + 32]) for i in range(start, end, 32)]), end
    values: list[Any] = []
    position = start
    if elem.dynamic:
        for _ in range(count):
            value, _end = _decode_value(elem, data, start + _read_word(data, position))
            values.append(value)
            position += 32
    else:
        for _ in range(count):
            value, position = _decode_value(elem, data, position)
            values.append(value)
    return tuple(values), position


# --- ABI JSON helpers ---------------------------------------------------------


def find_function(
    abi: Sequence[Mapping[str, Any]],
    name: str,
    args: Sequence[Any] = (),
) -> Mapping[str, Any]:
    """Resolve an overload by try-encoding the arguments.

    Raises :class:`AttributeError` when no function has that name (callers rely
    on this to trigger an indexer fallback) and :class:`AbiError` when the name
    exists but no overload accepts the arguments.
    """
    return _resolve(abi, name, args)[0]


def _resolve(
    abi: Sequence[Mapping[str, Any]],
    name: str,
    args: Sequence[Any],
) -> tuple[Mapping[str, Any], bytes]:
    """Return the first overload accepting ``args`` and the encoded arguments."""
    candidates = [
        entry
        for entry in abi
        if entry.get("type", "function") == "function" and entry.get("name") == name
    ]
    if not candidates:
        raise AttributeError(f"ABI has no function named {name!r}")

    failures: list[str] = []
    for entry in candidates:
        try:
            return entry, _encode_arguments(entry, args)
        except AbiError as exc:
            failures.append(str(exc))
    raise AbiError(
        f"no overload of {name!r} accepts {len(args)} argument(s): " + "; ".join(failures),
    )


def function_signature(function: Mapping[str, Any]) -> str:
    name = function.get("name")
    if not isinstance(name, str):
        raise AbiError(f"ABI function without a name: {function!r}")
    types = ",".join(canonical(item) for item in inputs_types(function))
    return f"{name}({types})"


def selector(function: Mapping[str, Any]) -> bytes:
    """4-byte selector, Keccak-256 of the canonical signature."""
    return _selector_of(function_signature(function))


@lru_cache(maxsize=1024)
def _selector_of(signature: str) -> bytes:
    return keccak256(signature.encode("ascii"))[:4]


def inputs_types(function: Mapping[str, Any]) -> tuple[AbiType, ...]:
    return tuple(type_from_abi(item) for item in function.get("inputs", ()) or ())


def outputs_types(function: Mapping[str, Any]) -> tuple[AbiType, ...]:
    return tuple(type_from_abi(item) for item in function.get("outputs", ()) or ())


def _encode_arguments(function: Mapping[str, Any], args: Sequence[Any]) -> bytes:
    return encode(inputs_types(function), args)


# --- primitive helpers --------------------------------------------------------


def _coerce_type(item: str | AbiType) -> AbiType:
    if isinstance(item, AbiType):
        return item
    if isinstance(item, str):
        return parse_type(item)
    raise AbiError(f"expected a type string or AbiType, got {type(item).__name__}")


def _to_word(value: int) -> bytes:
    return value.to_bytes(32, "big")


def _read_word(data: bytes, position: int) -> int:
    word = data[position : position + 32]
    if len(word) != 32 or position < 0:
        _require(data, position, 32)
    return int.from_bytes(word)


def _require(data: bytes, position: int, size: int) -> None:
    if position < 0 or position + size > len(data):
        raise AbiError(
            f"payload too short: need {size} byte(s) at offset {position}, "
            f"payload is {len(data)} byte(s)",
        )


def _ceil32(size: int) -> int:
    return (size + 31) // 32 * 32


def _as_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise AbiError(f"expected int for {label}, got {type(value).__name__}")
    return value


def _as_sequence(value: Any, label: str) -> Sequence[Any]:
    if isinstance(value, (list, tuple)):
        return value
    raise AbiError(f"expected list or tuple for {label}, got {type(value).__name__}")


def _as_bytes(value: Any) -> bytes:
    if isinstance(value, bytearray):
        return bytes(value)
    if isinstance(value, bytes):
        return value
    if isinstance(value, str):
        digits = value[2:] if value[:2].lower() == "0x" else value
        if len(digits) % 2 != 0:
            raise AbiError(f"hex string with odd length: {value!r}")
        try:
            raw = bytes.fromhex(digits)
        except ValueError as exc:
            raise AbiError(f"invalid hex value: {value!r}") from exc
        # ``bytes.fromhex`` skips ASCII whitespace; do not silently accept it.
        if raw.hex() != digits.lower():
            raise AbiError(f"invalid hex value: {value!r}")
        return raw
    raise AbiError(f"expected bytes or hex str, got {type(value).__name__}")


def _split_dimensions(type_str: str) -> tuple[str, list[int | None]]:
    base = type_str.strip()
    dimensions: list[int | None] = []
    while base.endswith("]"):
        opening = base.rfind("[")
        if opening == -1:
            raise AbiError(f"invalid array type {type_str!r}")
        inner = base[opening + 1 : -1].strip()
        if inner == "":
            dimensions.append(None)
        else:
            try:
                dimensions.append(int(inner))
            except ValueError as exc:
                raise AbiError(f"invalid array length in {type_str!r}") from exc
        base = base[:opening]
    dimensions.reverse()
    return base, dimensions


def _split_top_level(text: str) -> list[str]:
    parts: list[str] = []
    depth = 0
    current: list[str] = []
    for char in text:
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth < 0:
                raise AbiError(f"unbalanced parentheses in {text!r}")
        if char == "," and depth == 0:
            parts.append("".join(current).strip())
            current = []
        else:
            current.append(char)
    if depth != 0:
        raise AbiError(f"unbalanced parentheses in {text!r}")
    parts.append("".join(current).strip())
    return parts


def _simple_type(base: str) -> AbiType:
    if base == "address":
        return AbiType(kind="address")
    if base == "bool":
        return AbiType(kind="bool")
    if base == "string":
        return AbiType(kind="string")
    if base == "bytes":
        return AbiType(kind="bytes")
    if base == "function":
        return AbiType(kind="fixedbytes", size=24)
    if base.startswith(("uint", "int")) and base[-1].isdigit():
        kind = "uint" if base.startswith("uint") else "int"
        bits_text = base[len(kind) :]
        if not bits_text.isdigit():
            raise AbiError(f"invalid integer type {base!r}")
        bits = int(bits_text)
        if bits < 8 or bits > 256 or bits % 8 != 0:
            raise AbiError(f"invalid integer width in {base!r}")
        return AbiType(kind=kind, bits=bits)
    if base.startswith("bytes") and base[5:].isdigit():
        size = int(base[5:])
        if not 1 <= size <= 32:
            raise AbiError(f"invalid fixed bytes width in {base!r}")
        return AbiType(kind="fixedbytes", size=size)
    raise AbiError(f"unsupported ABI type {base!r}")
