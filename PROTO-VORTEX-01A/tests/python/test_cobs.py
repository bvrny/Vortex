"""COBS byte stuffing: output contains no 0x00; delimiter is appended by the
wire layer, not by cobs_encode itself. Vectors from the COBS paper/Wikipedia.
"""

import pytest

import vortex_protocol as vp


# (decoded, encoded) — canonical COBS examples, without trailing delimiter.
VECTORS = [
    (b"\x00", b"\x01\x01"),
    (b"\x00\x00", b"\x01\x01\x01"),
    (b"\x00\x11\x00", b"\x01\x02\x11\x01"),
    (b"\x11\x22\x00\x33", b"\x03\x11\x22\x02\x33"),
    (b"\x11\x22\x33\x44", b"\x05\x11\x22\x33\x44"),
    (b"\x11\x00\x00\x00", b"\x02\x11\x01\x01\x01"),
]


@pytest.mark.parametrize("decoded,encoded", VECTORS)
def test_cobs_encode_vectors(decoded, encoded):
    assert vp.cobs_encode(decoded) == encoded


@pytest.mark.parametrize("decoded,encoded", VECTORS)
def test_cobs_decode_vectors(decoded, encoded):
    assert vp.cobs_decode(encoded) == decoded


def test_cobs_encode_output_never_contains_zero():
    data = bytes(range(256)) * 3
    assert 0x00 not in vp.cobs_encode(data)


def test_cobs_roundtrip_254_nonzero_block_boundary():
    # 254 non-zero bytes is the max run per code byte; 254/255/256 exercise
    # the block-boundary logic where naive implementations break.
    for n in (253, 254, 255, 256, 509, 510):
        data = bytes((i % 255) + 1 for i in range(n))
        assert vp.cobs_decode(vp.cobs_encode(data)) == data


def test_cobs_roundtrip_all_zeros():
    data = b"\x00" * 300
    assert vp.cobs_decode(vp.cobs_encode(data)) == data


def test_cobs_decode_rejects_embedded_zero():
    with pytest.raises(ValueError):
        vp.cobs_decode(b"\x02\x00\x01")


def test_cobs_decode_rejects_truncated_block():
    # Code byte 0x05 promises 4 data bytes; only 2 follow.
    with pytest.raises(ValueError):
        vp.cobs_decode(b"\x05\x11\x22")
