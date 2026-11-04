"""Keccak-256.

Not SHA3-256: Ethereum uses the original Keccak padding, which the standard
library's ``hashlib.sha3_256`` does not implement. pycryptodome provides the C
implementation.
"""


def keccak256(data: bytes) -> bytes:
    from Crypto.Hash import keccak  # deferred: 14ms import

    digest = keccak.new(digest_bits=256)
    digest.update(data)
    return digest.digest()
