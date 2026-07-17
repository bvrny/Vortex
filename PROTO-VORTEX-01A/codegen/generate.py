#!/usr/bin/env python3
"""Vortex protocol code generator.

Reads protocol.yaml (single source of truth) and emits:
  generated/vortex_protocol.py  — consumed by the desktop app and simulator
  generated/vortex_protocol.h   — consumed by firmware and C host tests

Both artifacts carry a DO-NOT-EDIT banner and the SHA-256 of the source YAML
so drift is detectable. Run: python codegen/generate.py
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
YAML_PATH = ROOT / "protocol.yaml"
OUT_DIR = ROOT / "generated"

PARAM_TYPES = ("U8", "U16", "I16", "U32", "I32", "F32", "ENUM")


def load() -> tuple[dict, str]:
    text = YAML_PATH.read_text()
    return yaml.safe_load(text), hashlib.sha256(text.encode()).hexdigest()


def banner(sha: str, comment: str) -> str:
    c = comment
    return (
        f"{c} =============================================================\n"
        f"{c} GENERATED FILE — DO NOT EDIT.\n"
        f"{c} Source of truth: PROTO-VORTEX-01A/protocol.yaml\n"
        f"{c} Regenerate with: python PROTO-VORTEX-01A/codegen/generate.py\n"
        f"{c} protocol.yaml sha256: {sha}\n"
        f"{c} =============================================================\n"
    )


# --------------------------------------------------------------------------
# Python emission
# --------------------------------------------------------------------------

PY_RUNTIME = '''
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
    return cobs_encode(encode_frame(f)) + b"\\x00"


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
'''


def emit_python(spec: dict, sha: str) -> str:
    meta = spec["meta"]
    hw = spec["hardware"]
    lines: list[str] = []
    a = lines.append

    a('"""Vortex protocol — generated Python module."""')
    a(banner(sha, "#"))
    a("from __future__ import annotations")
    a("")
    a("import struct")
    a("from dataclasses import dataclass")
    a("from enum import IntEnum")
    a("")
    a(f"PROTOCOL_VERSION_MAJOR = {meta['version_major']}")
    a(f"PROTOCOL_VERSION_MINOR = {meta['version_minor']}")
    a(f"SYNC = 0x{meta['sync']:02X}")
    a(f"MAX_PAYLOAD = {meta['max_payload']}")
    a(f"FLAG_RESPONSE = 0x{spec['flags']['RESPONSE']:02X}")
    a(f"USB_VID = 0x{meta['usb_vid']:04X}")
    a(f"USB_PID = 0x{meta['usb_pid']:04X}")
    a(f"HEARTBEAT_TIMEOUT_MS = {meta['heartbeat_timeout_ms']}")
    a(f"HEARTBEAT_PERIOD_MS = {meta['heartbeat_period_ms']}")
    a("")
    a("# Hardware constants (mirrors of the design spec; see protocol.yaml)")
    a(f"FSW_HZ = {hw['fsw_hz']}")
    a(f"VREF_V = {hw['vref_v']}")
    a(f"DAC_FULLSCALE = {hw['dac_fullscale']}")
    a(f"CURRENT_SENSE_V_PER_A = {hw['current_sense_v_per_a']}")
    a(f"INA240_VREF_V = {hw['ina240_vref_v']}")
    a(f"VBUS_DIVIDER_K = {hw['vbus_divider_k']!r}")
    a(f"VBUS_OPERATING_MAX_V = {hw['vbus_operating_max_v']}")
    a(f"VBUS_SURVIVE_MAX_V = {hw['vbus_survive_max_v']}")
    a(f"BRAKE_TARGET_V = {hw['brake_target_v']}")
    a(f"BRAKE_BACKSTOP_V = {hw['brake_backstop_v']}")
    a("")

    a("class Cmd(IntEnum):")
    for name, val in spec["commands"].items():
        a(f"    {name} = 0x{val:02X}")
    a("")
    a("class Status(IntEnum):")
    for name, val in spec["status"].items():
        a(f"    {name} = {val}")
    a("")
    a("class ParamType(IntEnum):")
    for i, name in enumerate(PARAM_TYPES):
        a(f"    {name} = {i}")
    a("")
    for ename, vals in spec["enums"].items():
        a(f"class {ename}(IntEnum):")
        for name, val in vals.items():
            a(f"    {name} = {val}")
        a("")
    a("class Fault(IntEnum):")
    a('    """Bit positions in the u32 fault mask."""')
    for name, val in spec["faults"].items():
        a(f"    {name} = {val}")
    a("")
    a("FAULT_NAMES = {f.value: f.name for f in Fault}")
    a("")

    a("@dataclass(frozen=True)")
    a("class ParamMeta:")
    a("    id: int")
    a("    name: str")
    a("    type: ParamType")
    a("    unit: str")
    a("    min: float")
    a("    max: float")
    a("    default: float")
    a("    storage: str  # 'NV' | 'RAM'")
    a("    access: str   # 'RW' | 'RO'")
    a("    group: str")
    a("    enum_values: tuple = None")
    a("")
    a("@dataclass(frozen=True)")
    a("class ChannelMeta:")
    a("    bit: int")
    a("    name: str")
    a("    scale: float")
    a("    unit: str")
    a("")

    a("PARAMS = {")
    for p in spec["params"]:
        group = p["name"].split(".")[0]
        if p["type"] == "ENUM":
            enum_vals = tuple(p["enum"])
            pmin, pmax = 0, len(enum_vals) - 1
            enum_repr = repr(enum_vals)
        else:
            pmin, pmax = p["min"], p["max"]
            enum_repr = "None"
        a(
            f"    0x{p['id']:04X}: ParamMeta(id=0x{p['id']:04X}, name={p['name']!r}, "
            f"type=ParamType.{p['type']}, unit={p['unit']!r}, min={pmin!r}, max={pmax!r}, "
            f"default={p['default']!r}, storage={p['storage']!r}, access={p['access']!r}, "
            f"group={group!r}, enum_values={enum_repr}),"
        )
    a("}")
    a("")
    a("PARAM_BY_NAME = {m.name: m for m in PARAMS.values()}")
    a("")
    a("CHANNELS = [")
    for c in spec["telemetry"]["channels"]:
        a(
            f"    ChannelMeta(bit={c['bit']}, name={c['name']!r}, "
            f"scale={c['scale']!r}, unit={c['unit']!r}),"
        )
    a("]")
    a("")
    a("CHANNEL_BY_NAME = {c.name: c for c in CHANNELS}")

    return "\n".join(lines) + "\n" + PY_RUNTIME


# --------------------------------------------------------------------------
# C emission
# --------------------------------------------------------------------------

C_RUNTIME = r"""
/* ------------------------------------------------------------------ */
/* CRC16-CCITT-FALSE: poly 0x1021, init 0xFFFF, no reflect, no xorout */
/* ------------------------------------------------------------------ */
#define VP_CRC_INIT 0xFFFFu

static inline uint16_t vp_crc16(const uint8_t *data, size_t len, uint16_t crc)
{
    size_t i;
    for (i = 0u; i < len; i++) {
        uint8_t bit;
        crc ^= (uint16_t)((uint16_t)data[i] << 8);
        for (bit = 0u; bit < 8u; bit++) {
            if ((crc & 0x8000u) != 0u) {
                crc = (uint16_t)((uint16_t)(crc << 1) ^ 0x1021u);
            } else {
                crc = (uint16_t)(crc << 1);
            }
        }
    }
    return crc;
}

/* ------------------------------------------------------------------ */
/* COBS. dst must hold at least len + len/254 + 1 bytes.              */
/* ------------------------------------------------------------------ */
static inline size_t vp_cobs_encode(uint8_t *dst, const uint8_t *src, size_t len)
{
    size_t out = 1u;      /* index past the pending code byte */
    size_t code_idx = 0u;
    uint8_t code = 1u;
    size_t i;
    for (i = 0u; i < len; i++) {
        if (src[i] == 0u) {
            dst[code_idx] = code;
            code_idx = out;
            out++;
            code = 1u;
        } else {
            dst[out] = src[i];
            out++;
            code++;
            if (code == 0xFFu) {
                dst[code_idx] = code;
                code_idx = out;
                out++;
                code = 1u;
            }
        }
    }
    dst[code_idx] = code;
    return out;
}

/* Returns decoded length, or -1 on malformed input. */
static inline int32_t vp_cobs_decode(uint8_t *dst, const uint8_t *src, size_t len)
{
    size_t in = 0u;
    size_t out = 0u;
    while (in < len) {
        uint8_t code = src[in];
        uint8_t j;
        if (code == 0u) {
            return -1; /* embedded zero */
        }
        in++;
        if ((size_t)(code - 1u) > (len - in)) {
            return -1; /* truncated block */
        }
        for (j = 1u; j < code; j++) {
            if (src[in] == 0u) {
                return -1; /* embedded zero in block */
            }
            dst[out] = src[in];
            out++;
            in++;
        }
        if ((code != 0xFFu) && (in < len)) {
            dst[out] = 0u;
            out++;
        }
    }
    return (int32_t)out;
}

/* ------------------------------------------------------------------ */
/* Frame: [SYNC][VER][FLAGS][CMD][SEQ][LEN u16 LE][PAYLOAD][CRC16 LE] */
/* CRC over VER..PAYLOAD. Wire form = COBS(frame) + 0x00 delimiter.   */
/* ------------------------------------------------------------------ */
#define VP_FRAME_OVERHEAD 9u
#define VP_MAX_FRAME (VP_FRAME_OVERHEAD + VP_MAX_PAYLOAD)
/* COBS worst case: +1 byte per 254, +1 code byte, +1 wire delimiter */
#define VP_MAX_WIRE (VP_MAX_FRAME + (VP_MAX_FRAME / 254u) + 2u)

typedef struct {
    uint8_t ver;
    uint8_t flags;
    uint8_t cmd;
    uint8_t seq;
    uint16_t len;
    const uint8_t *payload; /* points into the decoder's buffer; copy before next feed */
} vp_frame_t;

/* Returns frame size, or -1 if cap is too small / payload too long. */
static inline int32_t vp_encode_frame(uint8_t *dst, size_t cap, uint8_t cmd,
                                      uint8_t seq, uint8_t flags,
                                      const uint8_t *payload, uint16_t len)
{
    uint16_t crc;
    size_t total = (size_t)VP_FRAME_OVERHEAD + (size_t)len;
    if ((len > VP_MAX_PAYLOAD) || (cap < total)) {
        return -1;
    }
    dst[0] = VP_SYNC;
    dst[1] = VP_PROTOCOL_VERSION_MAJOR;
    dst[2] = flags;
    dst[3] = cmd;
    dst[4] = seq;
    dst[5] = (uint8_t)(len & 0xFFu);
    dst[6] = (uint8_t)(len >> 8);
    if ((len > 0u) && (payload != NULL)) {
        (void)memcpy(&dst[7], payload, (size_t)len);
    }
    crc = vp_crc16(&dst[1], 6u + (size_t)len, VP_CRC_INIT);
    dst[7u + len] = (uint8_t)(crc & 0xFFu);
    dst[8u + len] = (uint8_t)(crc >> 8);
    return (int32_t)total;
}

/* Encodes frame + COBS + 0x00 delimiter into dst. Returns wire size or -1. */
static inline int32_t vp_encode_wire(uint8_t *dst, size_t cap, uint8_t cmd,
                                     uint8_t seq, uint8_t flags,
                                     const uint8_t *payload, uint16_t len)
{
    uint8_t frame[VP_MAX_FRAME];
    int32_t fsize = vp_encode_frame(frame, sizeof frame, cmd, seq, flags, payload, len);
    size_t wsize;
    if (fsize < 0) {
        return -1;
    }
    if (cap < ((size_t)fsize + ((size_t)fsize / 254u) + 2u)) {
        return -1;
    }
    wsize = vp_cobs_encode(dst, frame, (size_t)fsize);
    dst[wsize] = 0u;
    return (int32_t)(wsize + 1u);
}

/* Streaming decoder. No dynamic allocation; safe to feed from any context
 * EXCEPT the control ISR (frame handling belongs in the main loop). */
typedef struct {
    uint8_t buf[VP_MAX_WIRE];     /* raw COBS bytes of the current packet */
    uint16_t len;
    uint8_t overflow;             /* dropping until next delimiter */
    uint8_t decoded[VP_MAX_FRAME];
    uint16_t crc_errors;
    uint16_t len_errors;
    uint16_t cobs_errors;
    uint16_t sync_errors;
    uint16_t overflow_errors;
} vp_decoder_t;

static inline void vp_decoder_init(vp_decoder_t *d)
{
    (void)memset(d, 0, sizeof *d);
}

/* Feed one byte. Returns 1 when *out holds a complete valid frame
 * (out->payload points into d->decoded and is valid until the next feed
 * that completes a packet), else 0. Malformed packets are counted+dropped. */
static inline int vp_decoder_feed(vp_decoder_t *d, uint8_t byte, vp_frame_t *out)
{
    int32_t raw_len;
    uint16_t length;
    uint16_t crc_rx;
    uint16_t crc_calc;

    if (byte != 0u) {
        if (d->overflow != 0u) {
            return 0;
        }
        if (d->len >= (uint16_t)sizeof d->buf) {
            d->overflow = 1u;
            d->overflow_errors++;
            return 0;
        }
        d->buf[d->len] = byte;
        d->len++;
        return 0;
    }

    /* 0x00 delimiter: close out the packet */
    if (d->overflow != 0u) {
        d->overflow = 0u;
        d->len = 0u;
        return 0;
    }
    if (d->len == 0u) {
        return 0; /* idle delimiter */
    }
    raw_len = vp_cobs_decode(d->decoded, d->buf, (size_t)d->len);
    d->len = 0u;
    if (raw_len < 0) {
        d->cobs_errors++;
        return 0;
    }
    if (raw_len < (int32_t)VP_FRAME_OVERHEAD) {
        d->len_errors++;
        return 0;
    }
    if (d->decoded[0] != VP_SYNC) {
        d->sync_errors++;
        return 0;
    }
    length = (uint16_t)((uint16_t)d->decoded[5] | ((uint16_t)d->decoded[6] << 8));
    if ((int32_t)length != (raw_len - (int32_t)VP_FRAME_OVERHEAD)) {
        d->len_errors++;
        return 0;
    }
    crc_rx = (uint16_t)((uint16_t)d->decoded[7u + length] |
                        ((uint16_t)d->decoded[8u + length] << 8));
    crc_calc = vp_crc16(&d->decoded[1], 6u + (size_t)length, VP_CRC_INIT);
    if (crc_rx != crc_calc) {
        d->crc_errors++;
        return 0;
    }
    out->ver = d->decoded[1];
    out->flags = d->decoded[2];
    out->cmd = d->decoded[3];
    out->seq = d->decoded[4];
    out->len = length;
    out->payload = &d->decoded[7];
    return 1;
}
"""


def _c_float(v: float) -> str:
    return f"{v!r}f"


def _snake(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def emit_c(spec: dict, sha: str) -> str:
    meta = spec["meta"]
    hw = spec["hardware"]
    lines: list[str] = []
    a = lines.append

    a("/*")
    a(banner(sha, " *").rstrip())
    a(" */")
    a("#ifndef VORTEX_PROTOCOL_H")
    a("#define VORTEX_PROTOCOL_H")
    a("")
    a("#include <stdint.h>")
    a("#include <stddef.h>")
    a("#include <string.h>")
    a("")
    a("/* NOTE: header-only by design so firmware and host tests share one")
    a(" * artifact. Tables and functions are static; include from the few")
    a(" * translation units that need them. */")
    a("")
    a(f"#define VP_PROTOCOL_VERSION_MAJOR {meta['version_major']}u")
    a(f"#define VP_PROTOCOL_VERSION_MINOR {meta['version_minor']}u")
    a(f"#define VP_SYNC 0x{meta['sync']:02X}u")
    a(f"#define VP_MAX_PAYLOAD {meta['max_payload']}u")
    a(f"#define VP_FLAG_RESPONSE 0x{spec['flags']['RESPONSE']:02X}u")
    a(f"#define VP_USB_VID 0x{meta['usb_vid']:04X}u")
    a(f"#define VP_USB_PID 0x{meta['usb_pid']:04X}u")
    a("/* SAFETY-CRITICAL: link watchdog window while ARMED/RUNNING */")
    a(f"#define VP_HEARTBEAT_TIMEOUT_MS {meta['heartbeat_timeout_ms']}u")
    a(f"#define VP_HEARTBEAT_PERIOD_MS {meta['heartbeat_period_ms']}u")
    a("")
    a("/* Hardware constants (see protocol.yaml + design spec) */")
    a(f"#define VP_FSW_HZ {hw['fsw_hz']}u")
    a(f"#define VP_VREF_V {_c_float(hw['vref_v'])}")
    a(f"#define VP_DAC_FULLSCALE {hw['dac_fullscale']}u")
    a(f"#define VP_CURRENT_SENSE_V_PER_A {_c_float(hw['current_sense_v_per_a'])}")
    a(f"#define VP_INA240_VREF_V {_c_float(hw['ina240_vref_v'])}")
    a(f"#define VP_VBUS_DIVIDER_K {_c_float(hw['vbus_divider_k'])}")
    a(f"#define VP_VBUS_OPERATING_MAX_V {_c_float(hw['vbus_operating_max_v'])}")
    a(f"#define VP_VBUS_SURVIVE_MAX_V {_c_float(hw['vbus_survive_max_v'])}")
    a(f"#define VP_BRAKE_TARGET_V {_c_float(hw['brake_target_v'])}")
    a(f"#define VP_BRAKE_BACKSTOP_V {_c_float(hw['brake_backstop_v'])}")
    a("")

    a("typedef enum {")
    for name, val in spec["commands"].items():
        a(f"    VP_CMD_{name} = 0x{val:02X},")
    a("} vp_cmd_t;")
    a("")
    a("typedef enum {")
    for name, val in spec["status"].items():
        a(f"    VP_STATUS_{name} = {val},")
    a("} vp_status_t;")
    a("")
    a("typedef enum {")
    for i, name in enumerate(PARAM_TYPES):
        a(f"    VP_TYPE_{name} = {i},")
    a("} vp_param_type_t;")
    a("")
    for ename, vals in spec["enums"].items():
        prefix = _snake(ename).upper()
        a("typedef enum {")
        for name, val in vals.items():
            a(f"    VP_{prefix}_{name} = {val},")
        a(f"}} vp_{_snake(ename)}_t;")
        a("")
    a("/* Fault bit positions and masks (u32 fault mask on the wire) */")
    for name, val in spec["faults"].items():
        a(f"#define VP_FAULT_{name}_BIT {val}u")
        a(f"#define VP_FAULT_{name} (1uL << {val})")
    a("")

    a("typedef struct {")
    a("    uint16_t id;")
    a("    const char *name;")
    a("    vp_param_type_t type;")
    a("    const char *unit;")
    a("    float min;")
    a("    float max;")
    a("    float def_val;")
    a("    uint8_t is_nv;   /* 1 = persisted by PARAM_SAVE */")
    a("    uint8_t is_rw;   /* 1 = host-writable */")
    a("} vp_param_meta_t;")
    a("")
    a(f"#define VP_PARAM_COUNT {len(spec['params'])}u")
    a("static const vp_param_meta_t VP_PARAMS[VP_PARAM_COUNT] = {")
    for p in spec["params"]:
        if p["type"] == "ENUM":
            pmin, pmax = 0.0, float(len(p["enum"]) - 1)
        else:
            pmin, pmax = float(p["min"]), float(p["max"])
        nv = 1 if p["storage"] == "NV" else 0
        rw = 1 if p["access"] == "RW" else 0
        a(
            f'    {{ 0x{p["id"]:04X}u, "{p["name"]}", VP_TYPE_{p["type"]}, '
            f'"{p["unit"]}", {_c_float(pmin)}, {_c_float(pmax)}, '
            f'{_c_float(float(p["default"]))}, {nv}u, {rw}u }},'
        )
    a("};")
    a("")

    a("typedef struct {")
    a("    uint8_t bit;")
    a("    const char *name;")
    a("    float scale;  /* physical = raw_int16 * scale */")
    a("    const char *unit;")
    a("} vp_channel_meta_t;")
    a("")
    ch = spec["telemetry"]["channels"]
    a(f"#define VP_CHANNEL_COUNT {len(ch)}u")
    a("static const vp_channel_meta_t VP_CHANNELS[VP_CHANNEL_COUNT] = {")
    for c in ch:
        a(f'    {{ {c["bit"]}u, "{c["name"]}", {_c_float(float(c["scale"]))}, "{c["unit"]}" }},')
    a("};")
    a("")
    for c in ch:
        a(f"#define VP_CH_{c['name'].upper()} (1uL << {c['bit']})")

    return "\n".join(lines) + "\n" + C_RUNTIME + "\n#endif /* VORTEX_PROTOCOL_H */\n"


def main() -> None:
    spec, sha = load()

    ids = [p["id"] for p in spec["params"]]
    if len(ids) != len(set(ids)):
        raise SystemExit("duplicate param ids in protocol.yaml")
    cmds = list(spec["commands"].values())
    if len(cmds) != len(set(cmds)):
        raise SystemExit("duplicate command ids in protocol.yaml")
    bits = [c["bit"] for c in spec["telemetry"]["channels"]]
    if len(bits) != len(set(bits)):
        raise SystemExit("duplicate telemetry channel bits in protocol.yaml")
    for ename, vals in spec["enums"].items():
        if len(set(vals.values())) != len(vals):
            raise SystemExit(f"duplicate values in enum {ename} in protocol.yaml")
    fbits = list(spec["faults"].values())
    if len(fbits) != len(set(fbits)) or any(not 0 <= b < 32 for b in fbits):
        raise SystemExit("fault bits must be unique and in 0..31 in protocol.yaml")

    OUT_DIR.mkdir(exist_ok=True)
    (OUT_DIR / "vortex_protocol.py").write_text(emit_python(spec, sha))
    (OUT_DIR / "vortex_protocol.h").write_text(emit_c(spec, sha))
    print(f"generated vortex_protocol.py + vortex_protocol.h (yaml sha256 {sha[:12]})")


if __name__ == "__main__":
    main()
