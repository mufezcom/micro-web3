"""EIP-191 ``personal_sign`` hashing and secp256k1 signature recovery.

Wallets sign ``"\\x19Ethereum Signed Message:\\n" + len(message_bytes) +
message_bytes`` (version ``E``), where the length is the **UTF-8 byte count**
written in decimal ASCII, not the Python string length.

Recovery delegates to :mod:`ecdsa`'s secp256k1 implementation; this package
contains no elliptic-curve arithmetic. Signatures are the 65-byte ``r || s || v``
form that wallets return, with ``v`` as ``0``/``1`` (``yParity``) or ``27``/``28``
(and EIP-155 values ``>= 35``, which encode the parity in the low bit).
"""

from ecdsa import SECP256k1, VerifyingKey
from ecdsa.ecdsa import InvalidPointError, RSZeroError
from ecdsa.ellipticcurve import PointJacobi
from ecdsa.errors import MalformedPointError
from ecdsa.numbertheory import SquareRootError, inverse_mod, square_root_mod_prime
from ecdsa.util import sigdecode_string

from ._keccak import keccak256
from .addresses import to_checksum_address
from .errors import (
    MessageEncodingError,
    MessageTypeError,
    SignatureError,
    SignatureTypeError,
)

_PREFIX = b"\x19Ethereum Signed Message:\n"
_SIGNATURE_LENGTH = 65
_ORDER = SECP256k1.order


def personal_sign_hash(message: str | bytes | bytearray) -> bytes:
    """Return the EIP-191 (version ``E``) hash a wallet signs for ``message``.

    ``str`` messages are UTF-8 encoded; the header carries the byte length.
    Other types raise :class:`~micro_web3.errors.MessageTypeError` (a
    ``TypeError``). A ``str`` that cannot be UTF-8 encoded, e.g. one containing
    a lone surrogate from ``json.loads``, raises
    :class:`~micro_web3.errors.MessageEncodingError` (a ``UnicodeEncodeError``).
    """
    if isinstance(message, str):
        try:
            body = message.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise MessageEncodingError(exc) from exc
    elif isinstance(message, (bytes, bytearray)):
        body = bytes(message)
    else:
        raise MessageTypeError(f"message must be str or bytes, got {type(message).__name__}")
    return keccak256(_PREFIX + str(len(body)).encode("ascii") + body)


def recover_message_address(
    message: str | bytes | bytearray,
    signature: str | bytes | bytearray,
) -> str:
    """Return the EIP-55 address that produced ``signature`` over ``message``.

    ``signature`` is 65 bytes (``r || s || v``) as ``bytes`` or hex, with or
    without the ``0x`` prefix. Raises :class:`SignatureError` when the
    signature is malformed or no signer can be recovered. Messages follow
    :func:`personal_sign_hash`: non-``str``/``bytes`` values raise
    :class:`~micro_web3.errors.MessageTypeError` and an unencodable ``str``
    (lone surrogate) raises :class:`~micro_web3.errors.MessageEncodingError`.
    """
    recid, rs = _split_signature(signature)
    r = int.from_bytes(rs[:32], "big")
    s = int.from_bytes(rs[32:], "big")
    if not (0 < r < _ORDER and 0 < s < _ORDER):
        raise SignatureError("signature r and s must be in the range [1, secp256k1 order)")
    digest = personal_sign_hash(message)
    try:
        # ecdsa returns the candidate for the even-y R first and the odd-y R
        # second, i.e. in recovery-id order (see ``Signature.recover_public_keys``).
        candidates = VerifyingKey.from_public_key_recovery_with_digest(
            rs,
            digest,
            SECP256k1,
            hashfunc=None,
            sigdecode=sigdecode_string,
        )
        public_key = candidates[recid]
    except (TypeError, InvalidPointError):
        # ecdsa builds both candidates and fails when either is the point at
        # infinity, even if only the other one is requested. eth-account
        # recovers the requested candidate alone, so do the same here.
        try:
            public_key = VerifyingKey.from_public_point(
                _recover_point(r, s, digest, recid), SECP256k1, hashfunc=None
            )
        except (ArithmeticError, TypeError, ValueError, SquareRootError) as inner:
            raise SignatureError(f"signature recovery failed: {inner}") from inner
    except (
        ArithmeticError,
        MalformedPointError,
        RSZeroError,
        ValueError,
        SquareRootError,
    ) as exc:
        raise SignatureError(f"signature recovery failed: {exc}") from exc
    return to_checksum_address(keccak256(public_key.to_string("uncompressed")[1:])[-20:])


def _recover_point(r: int, s: int, digest: bytes, recid: int) -> PointJacobi:
    """Recover the public point for one recovery id, without its twin.

    Mirrors ``ecdsa.Signature.recover_public_keys`` for a single candidate; used
    only when the other candidate is the point at infinity.
    """
    curve = SECP256k1.curve
    p = curve.p()
    beta = square_root_mod_prime((pow(r, 3, p) + curve.b()) % p, p)
    y = beta if beta % 2 == recid else p - beta
    R = PointJacobi(curve, r, y, 1, _ORDER)
    e = int.from_bytes(digest, "big")
    point = inverse_mod(r, _ORDER) * (s * R + (-e % _ORDER) * SECP256k1.generator)
    if point.x() is None:
        raise SignatureError("signature recovers the point at infinity")
    return point


def _split_signature(signature: str | bytes | bytearray) -> tuple[int, bytes]:
    """Return ``(recovery_id, r || s)`` from a 65-byte signature."""
    if isinstance(signature, str):
        digits = signature[2:] if signature[:2].lower() == "0x" else signature
        try:
            raw = bytes.fromhex(digits)
        except ValueError as exc:
            raise SignatureError(f"invalid signature hex: {signature!r}") from exc
        # ``bytes.fromhex`` ignores ASCII whitespace; refuse anything that does
        # not round-trip so a padded signature is not silently accepted.
        if raw.hex() != digits.lower():
            raise SignatureError(f"invalid signature hex: {signature!r}")
    elif isinstance(signature, (bytes, bytearray)):
        raw = bytes(signature)
    else:
        raise SignatureTypeError(f"signature must be str or bytes, got {type(signature).__name__}")
    if len(raw) != _SIGNATURE_LENGTH:
        raise SignatureError(
            f"signature must be {_SIGNATURE_LENGTH} bytes (r || s || v), got {len(raw)}"
        )
    return _recovery_id(raw[64]), raw[:64]


def _recovery_id(v: int) -> int:
    if v in (0, 1):
        return v
    if v in (27, 28):
        return v - 27
    if v >= 35:
        return (v - 35) & 1
    raise SignatureError(f"invalid signature v: {v}; expected 0, 1, 27, 28 or an EIP-155 value")
