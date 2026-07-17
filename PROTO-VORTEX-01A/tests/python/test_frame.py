"""Frame layer: [SYNC 0xA5][VER][FLAGS][CMD][SEQ][LEN u16 LE][PAYLOAD][CRC16 LE]
CRC16-CCITT-FALSE over VER..PAYLOAD. On the wire the whole frame is
COBS-encoded and terminated with a single 0x00 delimiter.
"""

import struct

import pytest

import vortex_protocol as vp


def test_frame_encode_structure():
    f = vp.Frame(cmd=vp.Cmd.HELLO, payload=b"\x01\x02", seq=7)
    raw = vp.encode_frame(f)
    assert raw[0] == vp.SYNC == 0xA5
    assert raw[1] == vp.PROTOCOL_VERSION_MAJOR
    assert raw[2] == 0  # flags
    assert raw[3] == vp.Cmd.HELLO
    assert raw[4] == 7  # seq
    assert struct.unpack_from("<H", raw, 5)[0] == 2  # LEN little-endian
    assert raw[7:9] == b"\x01\x02"
    # CRC over VER..PAYLOAD, stored little-endian at the tail.
    crc = struct.unpack_from("<H", raw, 9)[0]
    assert crc == vp.crc16(raw[1:9])
    assert len(raw) == 11


def test_wire_encoding_is_cobs_plus_delimiter():
    f = vp.Frame(cmd=vp.Cmd.HEARTBEAT)
    wire = vp.encode_wire(f)
    assert wire[-1] == 0x00
    assert 0x00 not in wire[:-1]
    assert vp.cobs_decode(wire[:-1]) == vp.encode_frame(f)


def test_decoder_roundtrip_single_frame():
    f = vp.Frame(cmd=vp.Cmd.PARAM_READ, payload=b"\x01\x00", seq=42, flags=0)
    dec = vp.WireDecoder()
    frames = dec.feed(vp.encode_wire(f))
    assert len(frames) == 1
    out = frames[0]
    assert out.cmd == vp.Cmd.PARAM_READ
    assert out.payload == b"\x01\x00"
    assert out.seq == 42


def test_decoder_handles_split_delivery():
    # CDC-ACM delivers arbitrary chunk boundaries; the decoder must reassemble.
    f = vp.Frame(cmd=vp.Cmd.DEVICE_INFO, payload=bytes(range(1, 60)), seq=1)
    wire = vp.encode_wire(f)
    dec = vp.WireDecoder()
    got = []
    for i in range(0, len(wire), 3):
        got += dec.feed(wire[i : i + 3])
    assert len(got) == 1
    assert got[0].payload == bytes(range(1, 60))


def test_decoder_multiple_frames_in_one_feed():
    f1 = vp.Frame(cmd=vp.Cmd.ARM, seq=1)
    f2 = vp.Frame(cmd=vp.Cmd.STOP, seq=2)
    dec = vp.WireDecoder()
    frames = dec.feed(vp.encode_wire(f1) + vp.encode_wire(f2))
    assert [fr.cmd for fr in frames] == [vp.Cmd.ARM, vp.Cmd.STOP]


def test_decoder_resyncs_after_garbage():
    # Garbage (no 0x00) followed by a valid frame: the delimiter guarantees
    # resynchronization to the next error-free packet.
    f = vp.Frame(cmd=vp.Cmd.HEARTBEAT, seq=9)
    garbage = bytes(range(1, 100))  # no zeros
    dec = vp.WireDecoder()
    frames = dec.feed(garbage + b"\x00" + vp.encode_wire(f))
    assert len(frames) == 1
    assert frames[0].seq == 9


def test_decoder_rejects_bad_crc_and_counts_it():
    f = vp.Frame(cmd=vp.Cmd.ARM, seq=3)
    raw = bytearray(vp.encode_frame(f))
    raw[-1] ^= 0xFF  # corrupt CRC
    wire = vp.cobs_encode(bytes(raw)) + b"\x00"
    dec = vp.WireDecoder()
    assert dec.feed(wire) == []
    assert dec.crc_errors == 1


def test_decoder_rejects_len_mismatch():
    f = vp.Frame(cmd=vp.Cmd.ARM, seq=3)
    raw = bytearray(vp.encode_frame(f))
    raw[5] = 5  # claim 5 payload bytes that are not there
    wire = vp.cobs_encode(bytes(raw)) + b"\x00"
    dec = vp.WireDecoder()
    assert dec.feed(wire) == []
    assert dec.len_errors == 1


def test_decoder_survives_bad_frame_between_good_ones():
    good = vp.Frame(cmd=vp.Cmd.HEARTBEAT, seq=1)
    raw = bytearray(vp.encode_frame(good))
    raw[-1] ^= 0x55
    bad_wire = vp.cobs_encode(bytes(raw)) + b"\x00"
    dec = vp.WireDecoder()
    frames = dec.feed(vp.encode_wire(good) + bad_wire + vp.encode_wire(good))
    assert len(frames) == 2


def test_payload_too_long_rejected_on_encode():
    with pytest.raises(ValueError):
        vp.encode_frame(vp.Frame(cmd=vp.Cmd.HELLO, payload=b"x" * (vp.MAX_PAYLOAD + 1)))


def test_response_flag_constant():
    assert vp.FLAG_RESPONSE == 0x01


def test_command_ids_are_stable():
    # These numeric IDs are the wire contract; changing one is a breaking
    # protocol change and must bump PROTOCOL_VERSION_MAJOR.
    assert vp.Cmd.HELLO == 0x01
    assert vp.Cmd.DEVICE_INFO == 0x02
    assert vp.Cmd.PARAM_LIST == 0x10
    assert vp.Cmd.PARAM_READ == 0x11
    assert vp.Cmd.PARAM_WRITE == 0x12
    assert vp.Cmd.PARAM_SAVE == 0x13
    assert vp.Cmd.PARAM_LOAD == 0x14
    assert vp.Cmd.PARAM_DEFAULT == 0x15
    assert vp.Cmd.TELEMETRY_START == 0x20
    assert vp.Cmd.TELEMETRY_STOP == 0x21
    assert vp.Cmd.TELEMETRY_DATA == 0x22
    assert vp.Cmd.MOTOR_ID_START == 0x30
    assert vp.Cmd.MOTOR_ID_ABORT == 0x31
    assert vp.Cmd.MOTOR_ID_PROGRESS == 0x32
    assert vp.Cmd.PROTECTION_SET == 0x40
    assert vp.Cmd.FAULT_READ == 0x50
    assert vp.Cmd.FAULT_CLEAR == 0x51
    assert vp.Cmd.ARM == 0x60
    assert vp.Cmd.DISARM == 0x61
    assert vp.Cmd.STOP == 0x62
    assert vp.Cmd.SETPOINT == 0x63
    assert vp.Cmd.SCOPE_CONFIG == 0x70
    assert vp.Cmd.SCOPE_ARM == 0x71
    assert vp.Cmd.SCOPE_READ == 0x72
    assert vp.Cmd.REBOOT == 0x7D
    assert vp.Cmd.ENTER_DFU == 0x7E
    assert vp.Cmd.HEARTBEAT == 0x7F


def test_status_enum_values():
    assert vp.Status.OK == 0
    assert vp.Status.NACK_BAD_CRC == 1
    assert vp.Status.NACK_BAD_LEN == 2
    assert vp.Status.NACK_UNKNOWN_CMD == 3
    assert vp.Status.NACK_BAD_PARAM == 4
    assert vp.Status.NACK_BAD_STATE == 5
    assert vp.Status.NACK_OUT_OF_BOUNDS == 6
    assert vp.Status.BUSY == 7
