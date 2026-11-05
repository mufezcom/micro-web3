"""EIP-191 hashing and recovery, checked against eth-account 0.14 vectors.

Vectors were produced with ``eth_account.Account.sign_message(encode_defunct(text=...))``
and ``eth_account.messages._hash_eip191_message`` so the hand-rolled hashing and
the ecdsa recovery stay byte-compatible without a test dependency on eth-account.
"""

import pytest
from ecdsa import SECP256k1

from micro_web3 import (
    SignatureError,
    is_same_address,
    personal_sign_hash,
    recover_message_address,
)
from micro_web3._keccak import keccak256

SIWE = (
    "example.com wants you to sign in with your Ethereum account:\n"
    "0x2c7536E3605D9C16a7a3D7b1898e529396a65c23\n"
    "\n"
    "Sign in to example.com \u2014 \u3053\u3093\u306b\u3061\u306f"
)

# (keccak-256 of the EIP-191 payload, message)
HASHES = [
    ("b453bd4e271eed985cbab8231da609c4ce0a9cf1f763b6c1594e76315510e0f1", "Hello, world!"),
    ("1476abb745d423bf09273f1afd887d951181d25adc66c4834a70491911b7f750", "I\u2665SF"),
    ("5f35dce98ba4fba25530a026ed80b2cecdaa31091ba4958b99b52ea1d068adad", ""),
    ("1cace9d5f4644fe151828a6bb6a481e64443860984af1b89f7fbcb345d25c30b", SIWE),
    ("807a8dec4ed444e1c3f2775ff880ad2f6eb6322013fcf3acaf2b9abed5525ac9", "line1\nline2\r\n\ttab"),
]

# (signer, message, r || s || v)
SIGNATURES = [
    (
        "0x2c7536E3605D9C16a7a3D7b1898e529396a65c23",
        "Hello, world!",
        "2a73ec42acd33331635dcab78139d763b36ba303fc64940acd5f6797f83a78e1"
        "6cf49ce6937869cf5144c10c3bcfc07d25a3155cd96315176775c812f700173a1c",
    ),
    (
        "0x2c7536E3605D9C16a7a3D7b1898e529396a65c23",
        "I\u2665SF",
        "87f6856afaa7684bc6ecccef96246c155da984e7889dbdda1ae59940bdab8e67"
        "6cd3055bd38ac073cd5710e3040f1ed08073ca026266caeb097213d52665c4c01b",
    ),
    (
        "0x2c7536E3605D9C16a7a3D7b1898e529396a65c23",
        "",
        "8a68b4e66cd2b575338e16069d7b65f6f67c7ceae8945dccf8cb7bdb06278d93"
        "3dd9c888f3444ca4698464079a067ad3cfffe96d493b8ecf56885169d0fdfe7d1b",
    ),
    (
        "0x2c7536E3605D9C16a7a3D7b1898e529396a65c23",
        SIWE,
        "380870921b03d195da9afecfea23b9c280f347a2808b1200931a8b1e74c229c2"
        "6da7be94ab094c3e15e6841946ccfc2f30597fa83953d7bbca36b6567cbce4cb1c",
    ),
    (
        "0x2c7536E3605D9C16a7a3D7b1898e529396a65c23",
        "line1\nline2\r\n\ttab",
        "4110b00d0390f5f4382458659a28f2b67f010e8f2a2d5e65a7c04778ad4ddccf"
        "66f3fbca42da742131e54a760140870aee9117897fd5378933023db76e5eeeee1c",
    ),
    (
        "0x7E5F4552091A69125d5DfCb7b8C2659029395Bdf",
        "Hello, world!",
        "a3aa056cfa7a856e92ff89b37102ea536a4bfcf5ee5cc378a4ec840eff9713f3"
        "61b0532a453e2f11061bed9590bc27a9250cdea058ba4aa798aa1f0d2ea0b16d1c",
    ),
    (
        "0x7E5F4552091A69125d5DfCb7b8C2659029395Bdf",
        "I\u2665SF",
        "91980f9c86b486cd6c1df055764e629f120633793e544b1e884478567df2bdd2"
        "33c8c98c4743a80175a007a0ea373ec59e1860951e56ac478400f8d35cac38531b",
    ),
    (
        "0x7E5F4552091A69125d5DfCb7b8C2659029395Bdf",
        "",
        "0ac02a3eb3039b7a3ebb6a35f1e0dd31a4ed51781205a2c193354752a25edad5"
        "0593868baf38c519b78bdc61a23c3f55e058c29f8b83d79ae48cc47d931afaed1b",
    ),
    (
        "0x7E5F4552091A69125d5DfCb7b8C2659029395Bdf",
        SIWE,
        "d4cdad643c992f8e1e5f1c0d29bcce6e35fa6d867274d702e53688787762158b"
        "24c6d9ae38976a01e46b7b71f8a66e48ea27d2c8b1c9b53c90ae4c0e436f2ffd1b",
    ),
    (
        "0x7E5F4552091A69125d5DfCb7b8C2659029395Bdf",
        "line1\nline2\r\n\ttab",
        "5dae004b26a3ecead44c1c9f18f9807193c13cddbf555f96ff091abc2159e45a"
        "2fc48108097b6b7cc21b0d9a70ebfbe2fdfda64831803e045f9e6efd9fe883c41c",
    ),
    (
        "0x8fd379246834eac74B8419FfdA202CF8051F7A03",
        "Hello, world!",
        "c6e22b27c368d09c4fe4df8bb68f4125bf6c80b72cd0bf41c1b35edb161f9e11"
        "2ddc1ec47af343b1e7afdc5ed1e9cd9d7e49ed736a3e4281b8d404aadeed6fd01b",
    ),
    (
        "0x8fd379246834eac74B8419FfdA202CF8051F7A03",
        "I\u2665SF",
        "5d9e01ffd268541205e469b3e30a1bea143f4cbf1831f93a7cc618602c49ed16"
        "4f88aa628be6f67453b58d88a983b4e1b8728ea7551ed1f1cc5aa056bd330ead1b",
    ),
    (
        "0x8fd379246834eac74B8419FfdA202CF8051F7A03",
        "",
        "cbc77b540d6e4b8dd0c9fa86a6a5aedda35d391877ad98d34c748845b3f7df70"
        "5b604f681a6285df6ac222f06e3f76f67643d0461c6a3892f6efaa69ec27fe951b",
    ),
    (
        "0x8fd379246834eac74B8419FfdA202CF8051F7A03",
        SIWE,
        "830afd15e8eca99db7be7eb9ffbdbeb4df8e1701156f60f882c933606f9c0279"
        "42c454bde8da71ebb3f3951f7d37889f577c769ff9818ca8bc2942b64adae64c1b",
    ),
    (
        "0x8fd379246834eac74B8419FfdA202CF8051F7A03",
        "line1\nline2\r\n\ttab",
        "7ee27181c9b71d45885104dadf3d1bb41fa5953677a8d48ccda740157ce25d14"
        "0a3ec744266859f611e32ad8316e05b8f8950fc257285f9a2eeda3ed185eb29e1c",
    ),
]


@pytest.mark.parametrize(("digest", "message"), HASHES)
def test_personal_sign_hash_matches_eth_account(digest, message):
    assert personal_sign_hash(message).hex() == digest
    assert personal_sign_hash(message.encode()).hex() == digest


def test_personal_sign_hash_counts_utf8_bytes():
    # The header carries 6 bytes for "I♥SF" (4 characters), as EIP-191 requires.
    body = "I\u2665SF".encode()
    assert len(body) == 6
    assert personal_sign_hash("I\u2665SF") == keccak256(b"\x19Ethereum Signed Message:\n6" + body)
    char_count_header = b"\x19Ethereum Signed Message:\n4" + body
    assert personal_sign_hash("I\u2665SF") != keccak256(char_count_header)


@pytest.mark.parametrize(("signer", "message", "signature"), SIGNATURES)
def test_recover_message_address_matches_eth_account(signer, message, signature):
    assert recover_message_address(message, signature) == signer
    assert recover_message_address(message, "0x" + signature) == signer
    assert recover_message_address(message, bytes.fromhex(signature)) == signer


@pytest.mark.parametrize(("signer", "message", "signature"), SIGNATURES)
def test_recovery_accepts_y_parity_and_eip155_v(signer, message, signature):
    raw = bytes.fromhex(signature)
    parity = raw[64] - 27
    assert recover_message_address(message, raw[:64] + bytes([parity])) == signer
    for chain_id in (1, 5, 10, 50):
        v = 35 + 2 * chain_id + parity
        assert recover_message_address(message, raw[:64] + bytes([v])) == signer


def test_recovery_returns_checksummed_address():
    signer, message, signature = SIGNATURES[0]
    recovered = recover_message_address(message, signature)
    assert recovered == signer != signer.lower()


@pytest.mark.parametrize(
    "signature",
    [
        "0x1234",
        "zz" * 65,
        "0x" + "00" * 64,
        # v = 29 is neither a parity, a legacy v, nor EIP-155.
        "0x" + "11" * 64 + "1d",
        # v = 34 likewise.
        "0x" + "11" * 64 + "22",
        # r and s are out of range for secp256k1.
        "0x" + "ff" * 64 + "1b",
    ],
)
def test_bad_signatures_raise(signature):
    with pytest.raises(SignatureError):
        recover_message_address("hello", signature)


def test_signature_type_must_be_str_or_bytes():
    with pytest.raises(TypeError):
        recover_message_address("hello", 123)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("r", "s", "v"),
    [
        (0, 0, 27),  # both scalars zero
        (0, 1, 27),  # r zero
        (1, 0, 27),  # s zero; x = 1 is a valid curve point, so only the range check rejects it
        (5, 7, 27),  # x = 5 is not a curve x-coordinate, so no square root exists
        (SECP256k1.order + 2, 1, 27),  # r >= order, but ecdsa alone would still recover keys
    ],
)
def test_invalid_signature_scalars_are_rejected(r, s, v):
    signature = r.to_bytes(32, "big") + s.to_bytes(32, "big") + bytes([v])
    with pytest.raises(SignatureError):
        recover_message_address("hello", signature)


def test_flipping_s_and_y_parity_recovers_the_same_signer():
    signer, message, signature = SIGNATURES[0]
    raw = bytes.fromhex(signature)
    r = int.from_bytes(raw[:32], "big")
    s = int.from_bytes(raw[32:64], "big")
    high_s = r.to_bytes(32, "big") + (SECP256k1.order - s).to_bytes(32, "big")
    high_s += bytes([55 - raw[64]])
    assert recover_message_address(message, high_s) == signer


def test_signature_hex_with_whitespace_is_rejected():
    message, signature = SIGNATURES[0][1], SIGNATURES[0][2]
    # bytes.fromhex ignores the space, so this decodes to a valid 65-byte signature.
    spaced = "0x" + signature[:20] + " " + signature[20:]
    with pytest.raises(SignatureError):
        recover_message_address(message, spaced)


def test_unencodable_message_raises_unicode_encode_error():
    lone_surrogate = "\ud800"
    with pytest.raises(UnicodeEncodeError):
        personal_sign_hash(lone_surrogate)
    with pytest.raises(UnicodeEncodeError):
        recover_message_address(lone_surrogate, SIGNATURES[0][2])


@pytest.mark.parametrize("value", [5, 1.5, None, ["x"]])
def test_message_must_be_str_or_bytes(value):
    with pytest.raises(TypeError):
        personal_sign_hash(value)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        recover_message_address(value, SIGNATURES[0][2])  # type: ignore[arg-type]


def test_recovery_depends_on_the_message():
    signer, message, signature = SIGNATURES[0]
    assert recover_message_address(message + "!", signature) != signer


def test_signature_whose_recovered_key_is_infinity_is_rejected():
    # Pick R = 2G and s = e/k so that Q = (sR - eG) / r is the point at infinity.
    message = "x"
    k = 2
    r_point = k * SECP256k1.generator
    r = r_point.x() % SECP256k1.order
    digest = int.from_bytes(personal_sign_hash(message), "big") % SECP256k1.order
    s = digest * pow(k, -1, SECP256k1.order) % SECP256k1.order
    signature = r.to_bytes(32, "big") + s.to_bytes(32, "big") + bytes([27 + r_point.y() % 2])
    with pytest.raises(SignatureError):
        recover_message_address(message, signature)


def test_unused_infinity_candidate_matches_eth_account():
    # R = (e / s)G makes the candidate for the other y-parity the point at
    # infinity; eth-account still recovers the candidate that v selects.
    message = "hello"
    s = 7
    e = int.from_bytes(personal_sign_hash(message), "big") % SECP256k1.order
    r_point = (e * pow(s, -1, SECP256k1.order)) * SECP256k1.generator
    recid = 1 - r_point.y() % 2
    signature = r_point.x().to_bytes(32, "big") + s.to_bytes(32, "big")
    signature += bytes([27 + recid])
    assert (
        recover_message_address(message, signature) == "0xEDc921530385758d56c055220E77b30f88Cb8faE"
    )


def test_is_same_address():
    signer, _, _ = SIGNATURES[0]
    assert is_same_address(signer, signer.lower())
    assert is_same_address(signer.lower(), bytes.fromhex(signer[2:]))
    assert is_same_address("0x" + signer[2:].lower(), signer.upper().replace("0X", "0x"))
    assert not is_same_address(signer, SIGNATURES[5][0])


@pytest.mark.parametrize("value", ["0x1234", 42, None])
def test_is_same_address_rejects_malformed(value):
    with pytest.raises(ValueError):
        is_same_address(SIGNATURES[0][0], value)  # type: ignore[arg-type]
