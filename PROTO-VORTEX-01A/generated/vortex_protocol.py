"""Vortex protocol — generated Python module."""
# =============================================================
# GENERATED FILE — DO NOT EDIT.
# Source of truth: PROTO-VORTEX-01A/protocol.yaml
# Regenerate with: python PROTO-VORTEX-01A/codegen/generate.py
# protocol.yaml sha256: aaf60cde46dfceebb75eb0dc2986f788d1cfde5ad1aee46c5aef5c282c750c12
# =============================================================

from __future__ import annotations

import struct
from dataclasses import dataclass
from enum import IntEnum

PROTOCOL_VERSION_MAJOR = 1
PROTOCOL_VERSION_MINOR = 0
SYNC = 0xA5
MAX_PAYLOAD = 512
FLAG_RESPONSE = 0x01
USB_VID = 0x0483
USB_PID = 0x5740
HEARTBEAT_TIMEOUT_MS = 200
HEARTBEAT_PERIOD_MS = 50

# Hardware constants (mirrors of the design spec; see protocol.yaml)
FSW_HZ = 40000
VREF_V = 3.3
DAC_FULLSCALE = 4096
CURRENT_SENSE_V_PER_A = 0.005
INA240_VREF_V = 1.65
VBUS_DIVIDER_K = 0.0448901623686723
VBUS_OPERATING_MAX_V = 60.0
VBUS_SURVIVE_MAX_V = 70.0
BRAKE_TARGET_V = 63.0
BRAKE_BACKSTOP_V = 66.0

class Cmd(IntEnum):
    HELLO = 0x01
    DEVICE_INFO = 0x02
    PARAM_LIST = 0x10
    PARAM_READ = 0x11
    PARAM_WRITE = 0x12
    PARAM_SAVE = 0x13
    PARAM_LOAD = 0x14
    PARAM_DEFAULT = 0x15
    TELEMETRY_START = 0x20
    TELEMETRY_STOP = 0x21
    TELEMETRY_DATA = 0x22
    MOTOR_ID_START = 0x30
    MOTOR_ID_ABORT = 0x31
    MOTOR_ID_PROGRESS = 0x32
    PROTECTION_SET = 0x40
    FAULT_READ = 0x50
    FAULT_CLEAR = 0x51
    ARM = 0x60
    DISARM = 0x61
    STOP = 0x62
    SETPOINT = 0x63
    SCOPE_CONFIG = 0x70
    SCOPE_ARM = 0x71
    SCOPE_READ = 0x72
    REBOOT = 0x7D
    ENTER_DFU = 0x7E
    HEARTBEAT = 0x7F

class Status(IntEnum):
    OK = 0
    NACK_BAD_CRC = 1
    NACK_BAD_LEN = 2
    NACK_UNKNOWN_CMD = 3
    NACK_BAD_PARAM = 4
    NACK_BAD_STATE = 5
    NACK_OUT_OF_BOUNDS = 6
    BUSY = 7

class ParamType(IntEnum):
    U8 = 0
    U16 = 1
    I16 = 2
    U32 = 3
    I32 = 4
    F32 = 5
    ENUM = 6

class DeviceState(IntEnum):
    INIT = 0
    PRECHARGE = 1
    SELFTEST = 2
    STANDBY = 3
    ARMED = 4
    RUNNING = 5
    FAULT = 6

class SetpointMode(IntEnum):
    TORQUE = 0
    SPEED = 1

class MotorIdStage(IntEnum):
    IDLE = 0
    RESISTANCE = 1
    INDUCTANCE = 2
    FLUX = 3
    DONE = 4
    FAILED = 5

class TrigEdge(IntEnum):
    RISING = 0
    FALLING = 1

class Fault(IntEnum):
    """Bit positions in the u32 fault mask."""
    OVERCURRENT = 0
    OVERVOLTAGE = 1
    UNDERVOLTAGE = 2
    OVERTEMP_INV = 3
    OVERTEMP_MOTOR = 4
    HALL_FAULT = 5
    PHASE_LOSS = 6
    HEARTBEAT_LOSS = 7
    GATE_DRIVER = 8
    SELFTEST_FAIL = 9
    OVERSPEED = 10
    BRAKE_BACKSTOP = 11

FAULT_NAMES = {f.value: f.name for f in Fault}

@dataclass(frozen=True)
class ParamMeta:
    id: int
    name: str
    type: ParamType
    unit: str
    min: float
    max: float
    default: float
    storage: str  # 'NV' | 'RAM'
    access: str   # 'RW' | 'RO'
    group: str
    enum_values: tuple = None

@dataclass(frozen=True)
class ChannelMeta:
    bit: int
    name: str
    scale: float
    unit: str

PARAMS = {
    0x0001: ParamMeta(id=0x0001, name='motor.pole_pairs', type=ParamType.U8, unit='', min=1, max=64, default=7, storage='NV', access='RW', group='motor', enum_values=None),
    0x0002: ParamMeta(id=0x0002, name='motor.r_phase', type=ParamType.F32, unit='ohm', min=0.0005, max=2.0, default=0.02, storage='NV', access='RW', group='motor', enum_values=None),
    0x0003: ParamMeta(id=0x0003, name='motor.l_d', type=ParamType.F32, unit='H', min=1e-06, max=0.01, default=2e-05, storage='NV', access='RW', group='motor', enum_values=None),
    0x0004: ParamMeta(id=0x0004, name='motor.l_q', type=ParamType.F32, unit='H', min=1e-06, max=0.01, default=2e-05, storage='NV', access='RW', group='motor', enum_values=None),
    0x0005: ParamMeta(id=0x0005, name='motor.flux_lambda', type=ParamType.F32, unit='Wb', min=0.0001, max=1.0, default=0.005, storage='NV', access='RW', group='motor', enum_values=None),
    0x0101: ParamMeta(id=0x0101, name='iloop.kp', type=ParamType.F32, unit='V/A', min=0.0, max=100.0, default=0.3351, storage='NV', access='RW', group='iloop', enum_values=None),
    0x0102: ParamMeta(id=0x0102, name='iloop.ki', type=ParamType.F32, unit='V/(A.s)', min=0.0, max=1000000.0, default=335.1, storage='NV', access='RW', group='iloop', enum_values=None),
    0x0103: ParamMeta(id=0x0103, name='iloop.bandwidth_hz', type=ParamType.F32, unit='Hz', min=2000.0, max=4000.0, default=2666.667, storage='NV', access='RW', group='iloop', enum_values=None),
    0x0104: ParamMeta(id=0x0104, name='iloop.lpf_tf', type=ParamType.F32, unit='s', min=1e-06, max=0.01, default=1.194e-05, storage='NV', access='RW', group='iloop', enum_values=None),
    0x0201: ParamMeta(id=0x0201, name='prot.overcurrent_a', type=ParamType.F32, unit='A', min=10.0, max=175.0, default=150.0, storage='NV', access='RW', group='prot', enum_values=None),
    0x0202: ParamMeta(id=0x0202, name='prot.overvoltage_v', type=ParamType.F32, unit='V', min=63.5, max=65.5, default=65.0, storage='NV', access='RW', group='prot', enum_values=None),
    0x0301: ParamMeta(id=0x0301, name='sensor.mode', type=ParamType.ENUM, unit='', min=0, max=2, default=0, storage='NV', access='RW', group='sensor', enum_values=('hall', 'encoder', 'sensorless')),
    0x0302: ParamMeta(id=0x0302, name='sensor.hall_offset_deg', type=ParamType.F32, unit='deg', min=-180.0, max=180.0, default=0.0, storage='NV', access='RW', group='sensor', enum_values=None),
    0x0303: ParamMeta(id=0x0303, name='sensor.hall_sequence', type=ParamType.U8, unit='', min=0, max=5, default=0, storage='NV', access='RW', group='sensor', enum_values=None),
    0x0311: ParamMeta(id=0x0311, name='sensor.enc_cpr', type=ParamType.I32, unit='counts', min=1, max=1000000, default=4096, storage='NV', access='RW', group='sensor', enum_values=None),
    0x0312: ParamMeta(id=0x0312, name='sensor.enc_offset_deg', type=ParamType.F32, unit='deg', min=-180.0, max=180.0, default=0.0, storage='NV', access='RW', group='sensor', enum_values=None),
    0x0313: ParamMeta(id=0x0313, name='sensor.enc_direction', type=ParamType.U8, unit='', min=0, max=1, default=0, storage='NV', access='RW', group='sensor', enum_values=None),
    0x0321: ParamMeta(id=0x0321, name='sensor.obs_gain', type=ParamType.F32, unit='', min=0.0, max=1000000.0, default=100.0, storage='NV', access='RW', group='sensor', enum_values=None),
    0x0401: ParamMeta(id=0x0401, name='limits.i_max_a', type=ParamType.F32, unit='A', min=1.0, max=175.0, default=120.0, storage='NV', access='RW', group='limits', enum_values=None),
    0x0402: ParamMeta(id=0x0402, name='limits.vbus_min_v', type=ParamType.F32, unit='V', min=15.0, max=60.0, default=20.0, storage='NV', access='RW', group='limits', enum_values=None),
    0x0403: ParamMeta(id=0x0403, name='limits.vbus_max_v', type=ParamType.F32, unit='V', min=20.0, max=60.0, default=60.0, storage='NV', access='RW', group='limits', enum_values=None),
    0x0404: ParamMeta(id=0x0404, name='limits.temp_inv_max_c', type=ParamType.F32, unit='degC', min=40.0, max=110.0, default=90.0, storage='NV', access='RW', group='limits', enum_values=None),
    0x0405: ParamMeta(id=0x0405, name='limits.temp_motor_max_c', type=ParamType.F32, unit='degC', min=40.0, max=180.0, default=120.0, storage='NV', access='RW', group='limits', enum_values=None),
    0x0406: ParamMeta(id=0x0406, name='limits.speed_max_rpm', type=ParamType.F32, unit='rpm', min=100.0, max=30000.0, default=5000.0, storage='NV', access='RW', group='limits', enum_values=None),
    0x0501: ParamMeta(id=0x0501, name='telem.default_mask', type=ParamType.U32, unit='', min=0, max=4294967295, default=455, storage='NV', access='RW', group='telem', enum_values=None),
    0x0502: ParamMeta(id=0x0502, name='telem.default_decimation', type=ParamType.U16, unit='', min=1, max=40000, default=8, storage='NV', access='RW', group='telem', enum_values=None),
}

PARAM_BY_NAME = {m.name: m for m in PARAMS.values()}

CHANNELS = [
    ChannelMeta(bit=0, name='ia', scale=0.01, unit='A'),
    ChannelMeta(bit=1, name='ib', scale=0.01, unit='A'),
    ChannelMeta(bit=2, name='ic', scale=0.01, unit='A'),
    ChannelMeta(bit=3, name='va', scale=0.0025, unit='V'),
    ChannelMeta(bit=4, name='vb', scale=0.0025, unit='V'),
    ChannelMeta(bit=5, name='vc', scale=0.0025, unit='V'),
    ChannelMeta(bit=6, name='vbus', scale=0.0025, unit='V'),
    ChannelMeta(bit=7, name='id', scale=0.01, unit='A'),
    ChannelMeta(bit=8, name='iq', scale=0.01, unit='A'),
    ChannelMeta(bit=9, name='vd', scale=0.0025, unit='V'),
    ChannelMeta(bit=10, name='vq', scale=0.0025, unit='V'),
    ChannelMeta(bit=11, name='angle_elec', scale=9.587379924285257e-05, unit='rad'),
    ChannelMeta(bit=12, name='speed', scale=1.0, unit='rpm'),
    ChannelMeta(bit=13, name='iq_setpoint', scale=0.01, unit='A'),
    ChannelMeta(bit=14, name='temp_inv1', scale=0.01, unit='degC'),
    ChannelMeta(bit=15, name='temp_inv2', scale=0.01, unit='degC'),
    ChannelMeta(bit=16, name='temp_inv3', scale=0.01, unit='degC'),
    ChannelMeta(bit=17, name='temp_motor', scale=0.01, unit='degC'),
]

CHANNEL_BY_NAME = {c.name: c for c in CHANNELS}

_STRUCT_BY_TYPE = {
    ParamType.U8: "<B", ParamType.U16: "<H", ParamType.I16: "<h",
    ParamType.U32: "<I", ParamType.I32: "<i", ParamType.F32: "<f",
    ParamType.ENUM: "<B",
}


def crc16(data: bytes, crc: int = 0xFFFF) -> int:
    """CRC16-CCITT-FALSE: poly 0x1021, init 0xFFFF, no reflection, no xorout."""
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


def cobs_encode(data: bytes) -> bytes:
    """COBS-encode; output contains no 0x00. Delimiter is NOT appended."""
    out = bytearray(1)  # placeholder for first code byte
    code_idx = 0
    code = 1
    for b in data:
        if b == 0:
            out[code_idx] = code
            code_idx = len(out)
            out.append(0)
            code = 1
        else:
            out.append(b)
            code += 1
            if code == 0xFF:
                out[code_idx] = code
                code_idx = len(out)
                out.append(0)
                code = 1
    out[code_idx] = code
    return bytes(out)


def cobs_decode(data: bytes) -> bytes:
    """Inverse of cobs_encode. Raises ValueError on malformed input."""
    out = bytearray()
    i = 0
    while i < len(data):
        code = data[i]
        if code == 0:
            raise ValueError("COBS: embedded zero code byte")
        i += 1
        block = data[i : i + code - 1]
        if len(block) != code - 1:
            raise ValueError("COBS: truncated block")
        if 0 in block:
            raise ValueError("COBS: embedded zero in block")
        out += block
        i += code - 1
        if code != 0xFF and i < len(data):
            out.append(0)
    return bytes(out)


@dataclass
class Frame:
    """One protocol frame (pre-COBS representation)."""

    cmd: int
    payload: bytes = b""
    seq: int = 0
    flags: int = 0
    ver: int = PROTOCOL_VERSION_MAJOR


def encode_frame(f: Frame) -> bytes:
    """[SYNC][VER][FLAGS][CMD][SEQ][LEN u16 LE][PAYLOAD][CRC16 LE].

    CRC16-CCITT-FALSE over VER..PAYLOAD (everything after SYNC, before CRC).
    """
    if len(f.payload) > MAX_PAYLOAD:
        raise ValueError(f"payload {len(f.payload)} exceeds MAX_PAYLOAD {MAX_PAYLOAD}")
    head = struct.pack("<BBBBBH", SYNC, f.ver, f.flags, int(f.cmd), f.seq, len(f.payload))
    crc = crc16(head[1:] + f.payload)
    return head + f.payload + struct.pack("<H", crc)


def encode_wire(f: Frame) -> bytes:
    """Wire form: COBS(frame) + 0x00 delimiter."""
    return cobs_encode(encode_frame(f)) + b"\x00"


class WireDecoder:
    """Streaming decoder: feed arbitrary chunks, get complete valid frames.

    Malformed packets are dropped and counted; the 0x00 delimiter guarantees
    resynchronization on the next error-free packet.
    """

    def __init__(self) -> None:
        self._buf = bytearray()
        self.crc_errors = 0
        self.len_errors = 0
        self.cobs_errors = 0
        self.sync_errors = 0

    def feed(self, data: bytes) -> list[Frame]:
        self._buf += data
        frames: list[Frame] = []
        while True:
            i = self._buf.find(0)
            if i < 0:
                break
            chunk = bytes(self._buf[:i])
            del self._buf[: i + 1]
            if not chunk:
                continue
            frame = self._parse(chunk)
            if frame is not None:
                frames.append(frame)
        return frames

    def _parse(self, chunk: bytes) -> Frame | None:
        try:
            raw = cobs_decode(chunk)
        except ValueError:
            self.cobs_errors += 1
            return None
        if len(raw) < 9:
            self.len_errors += 1
            return None
        if raw[0] != SYNC:
            self.sync_errors += 1
            return None
        ver, flags, cmd, seq = raw[1], raw[2], raw[3], raw[4]
        (length,) = struct.unpack_from("<H", raw, 5)
        if length != len(raw) - 9:
            self.len_errors += 1
            return None
        (crc,) = struct.unpack_from("<H", raw, 7 + length)
        if crc != crc16(raw[1 : 7 + length]):
            self.crc_errors += 1
            return None
        try:
            cmd = Cmd(cmd)
        except ValueError:
            pass  # unknown command ids are delivered as plain ints
        return Frame(cmd=cmd, payload=bytes(raw[7 : 7 + length]), seq=seq, flags=flags, ver=ver)


def encode_param_value(meta: ParamMeta, value) -> bytes:
    return struct.pack(_STRUCT_BY_TYPE[meta.type], value)


def decode_param_value(meta: ParamMeta, data: bytes):
    return struct.unpack(_STRUCT_BY_TYPE[meta.type], data)[0]


def decode_faults(mask: int) -> list:
    """Fault names for the set bits, in ascending bit order."""
    return [FAULT_NAMES[b] for b in sorted(FAULT_NAMES) if mask & (1 << b)]


@dataclass
class TelemetryBatch:
    base_timestamp_us: int
    channel_mask: int
    decimation: int
    samples: list  # [(t_offset_us, (int16, ...)), ...] values in ascending bit order


def active_channels(mask: int) -> list:
    """ChannelMeta list for the mask, in ascending bit order (= wire order)."""
    return [c for c in CHANNELS if mask & (1 << c.bit)]


def build_telemetry(base_timestamp_us: int, channel_mask: int, decimation: int,
                    samples: list) -> bytes:
    n = bin(channel_mask).count("1")
    out = bytearray(struct.pack("<IIHH", base_timestamp_us, channel_mask,
                                len(samples), decimation))
    fmt = "<H%dh" % n
    for t_off, vals in samples:
        if len(vals) != n:
            raise ValueError(f"sample has {len(vals)} values, mask expects {n}")
        out += struct.pack(fmt, t_off, *vals)
    return bytes(out)


def parse_telemetry(payload: bytes) -> TelemetryBatch:
    if len(payload) < 12:
        raise ValueError("telemetry payload shorter than header")
    base, mask, n_samples, dec = struct.unpack_from("<IIHH", payload, 0)
    n = bin(mask).count("1")
    step = 2 + 2 * n
    if len(payload) != 12 + n_samples * step:
        raise ValueError("telemetry payload length mismatch")
    fmt = "<H%dh" % n
    samples = []
    off = 12
    for _ in range(n_samples):
        vals = struct.unpack_from(fmt, payload, off)
        samples.append((vals[0], tuple(vals[1:])))
        off += step
    return TelemetryBatch(base, mask, dec, samples)
