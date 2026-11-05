import pytest

from micro_web3 import is_address, is_same_address, to_checksum_address

# EIP-55 vectors.
EIP55 = [
    "0x52908400098527886E0F7030069857D2E4169EE7",
    "0x8617E340B3D01FA5F11F306F4090FD50E238070D",
    "0xde709f2102306220921060314715629080e2fb77",
    "0x27b1fdb04752bbc536007a920d24acb045561c26",
    "0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAed",
    "0xfB6916095ca1df60bB79Ce92cE3Ea74c37c5d359",
    "0xdbF03B407c01E7cD3CBea99509d93f8DDDC8C6FB",
    "0xD1220A0cf47c7B9Be7A2E6BA89F429762e7b9aDb",
]


@pytest.mark.parametrize("expected", EIP55)
def test_checksum_matches_eip55(expected):
    assert to_checksum_address(expected.lower()) == expected
    assert to_checksum_address(expected.upper().replace("0X", "0x")) == expected
    assert to_checksum_address(bytes.fromhex(expected[2:])) == expected


def test_checksum_accepts_bare_hex():
    assert to_checksum_address(EIP55[0][2:]) == EIP55[0]


@pytest.mark.parametrize(
    "value",
    ["0x1234", "0x" + "zz" * 20, "0x" + "00" * 19, 1234, None],
)
def test_invalid_addresses(value):
    with pytest.raises((TypeError, ValueError)):
        to_checksum_address(value)


def test_is_address():
    assert is_address(EIP55[0])
    assert is_address(bytes.fromhex(EIP55[0][2:]))
    assert not is_address("0x1234")
    assert not is_address(42)


def test_addresses_with_whitespace_are_rejected():
    body = EIP55[0][2:]
    # A 40-character hex body, but bytes.fromhex() drops the spaces and yields 19 bytes.
    spaced = "0x" + body[:8] + " " + body[8:18] + " " + body[18:38]
    assert len(spaced) == 42
    assert not is_address(spaced)
    with pytest.raises(ValueError):
        to_checksum_address(spaced)
    with pytest.raises(ValueError):
        is_same_address(spaced, spaced)
    with pytest.raises(ValueError):
        is_same_address(EIP55[0], spaced)
