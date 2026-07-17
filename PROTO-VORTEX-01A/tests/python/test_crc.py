"""CRC16-CCITT-FALSE: poly 0x1021, init 0xFFFF, no reflection, no xorout."""

import vortex_protocol as vp


def test_crc_known_check_value():
    # Standard check value for CRC-16/CCITT-FALSE.
    assert vp.crc16(b"123456789") == 0x29B1


def test_crc_empty_is_init():
    assert vp.crc16(b"") == 0xFFFF


def test_crc_incremental_equals_oneshot():
    data = bytes(range(256))
    partial = vp.crc16(data[:100])
    assert vp.crc16(data[100:], crc=partial) == vp.crc16(data)


def test_crc_detects_single_bit_flip():
    data = b"vortex telemetry frame"
    good = vp.crc16(data)
    corrupted = bytes([data[0] ^ 0x01]) + data[1:]
    assert vp.crc16(corrupted) != good
