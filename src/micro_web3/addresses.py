"""Address helpers.

Decoding follows eth_abi and returns lower-case ``0x`` hex; checksumming is
opt-in through :func:`to_checksum_address` (EIP-55).
"""

from ._keccak import keccak256


def to_bytes20(value: str | bytes | bytearray) -> bytes:
    """Validate and return the 20 raw bytes of an address."""
    if isinstance(value, bytearray):
        value = bytes(value)
    if isinstance(value, bytes):
        if len(value) != 20:
            raise ValueError(f"address must be 20 bytes, got {len(value)}")
        return value
    if not isinstance(value, str):
        raise TypeError(f"address must be str or bytes, got {type(value).__name__}")
    digits = value[2:] if value[:2].lower() == "0x" else value
    if len(digits) != 40:
        raise ValueError(f"address must be 20 bytes, got {len(digits) // 2} bytes")
    try:
        return bytes.fromhex(digits)
    except ValueError as exc:
        raise ValueError(f"invalid address: {value!r}") from exc


def to_checksum_address(value: str | bytes | bytearray) -> str:
    """Return the EIP-55 mixed-case form of ``value``."""
    raw = to_bytes20(value)
    lower = raw.hex()
    digest = keccak256(lower.encode("ascii")).hex()
    checksummed = "".join(
        char.upper() if char.isalpha() and int(digest[i], 16) >= 8 else char
        for i, char in enumerate(lower)
    )
    return "0x" + checksummed


def is_address(value: object) -> bool:
    """True if ``value`` is a well-formed 20-byte address."""
    if not isinstance(value, (str, bytes, bytearray)):
        return False
    try:
        to_bytes20(value)
    except ValueError:
        return False
    return True
