# Vortex USB Protocol — Payload Contract

Normative companion to [`protocol.yaml`](protocol.yaml) (the single source of
truth for every numeric ID, parameter, telemetry channel, enum, and fault bit).
This document defines what `protocol.yaml` cannot express: the **byte layout of
each command's payload** and the transaction rules. Firmware
(`FW-VECTOR-01B`), the desktop app, and the device simulator (`APP-VORTEX`)
all implement against this file plus the generated modules
(`generated/vortex_protocol.{py,h}` — regenerate with
`python codegen/generate.py`).

All multi-byte fields are **little-endian**. Changing any layout here is a
breaking protocol change: bump `meta.version_major` in `protocol.yaml`.

## 1. Framing (recap)

```
frame = [SYNC 0xA5][VER u8][FLAGS u8][CMD u8][SEQ u8][LEN u16][PAYLOAD ...][CRC16 u16]
wire  = COBS(frame) + 0x00
```

- CRC16-CCITT-FALSE (poly 0x1021, init 0xFFFF) over `VER..PAYLOAD`.
- `LEN` = payload byte count, max `meta.max_payload` (512).
- The 0x00 delimiter guarantees decoder resynchronization after corruption.

## 2. Transaction model

- Host→device frames are **requests**; the device answers every request
  (except noted) with one frame that echoes `CMD` and `SEQ` and sets
  `FLAG_RESPONSE` (0x01).
- **Every response payload begins with `status u8`** (`Status` enum). On any
  status ≠ `OK`, the response payload is the status byte alone unless stated
  otherwise.
- Device→host **unsolicited** frames (`TELEMETRY_DATA`, `MOTOR_ID_PROGRESS`)
  have `FLAG_RESPONSE` clear, `SEQ` incrementing per stream, and are never
  acknowledged by the host.
- `SEQ` is a free-running per-sender counter; the host uses it to match
  responses to requests.

## 3. Command payloads

`value` fields use the parameter's wire type from `protocol.yaml`
(`encode_param_value` / `decode_param_value`). Enum fields travel as `u8`.

| Command | Request payload | OK-response payload (after `status u8`) |
|---|---|---|
| `HELLO` | — | `proto_major u8, proto_minor u8` |
| `DEVICE_INFO` | — | `fw_major u8, fw_minor u8, fw_patch u8, uid u8[12], name utf-8…` |
| `PARAM_LIST` | — | `count u16, id u16 × count` |
| `PARAM_READ` | `id u16` | `id u16, value` |
| `PARAM_WRITE` | `id u16, value` | `id u16` |
| `PARAM_SAVE` | — | — |
| `PARAM_LOAD` | — | — |
| `PARAM_DEFAULT` | — | — |
| `TELEMETRY_START` | `mask u32, decimation u16` | — |
| `TELEMETRY_STOP` | — | — |
| `TELEMETRY_DATA` | *(device→host, unsolicited)* payload = telemetry batch, §4 | *(no response)* |
| `MOTOR_ID_START` | — | — |
| `MOTOR_ID_ABORT` | — | — |
| `MOTOR_ID_PROGRESS` | *(device→host, unsolicited)* `stage u8 (MotorIdStage), percent u8, r_phase f32, l_d f32, l_q f32, flux f32` (results valid once `stage == DONE`, else 0) | *(no response)* |
| `PROTECTION_SET` | `overcurrent_a f32, overvoltage_v f32` | — |
| `FAULT_READ` | — | `active u32, latched u32` (Fault bit masks) |
| `FAULT_CLEAR` | — | — |
| `ARM` | — | — |
| `DISARM` | — | — |
| `STOP` | — | — |
| `SETPOINT` | `mode u8 (SetpointMode), value f32` | — |
| `SCOPE_CONFIG` | `mask u32, decimation u16, pretrigger u16, trig_channel u8, trig_edge u8 (TrigEdge), trig_level i16 (raw)` | — |
| `SCOPE_ARM` | — | — |
| `SCOPE_READ` | `offset u32` | `total u32, offset u32, data u8…` (chunk ≤ `MAX_PAYLOAD − 9`; repeat with growing offset until `offset + len(data) == total`; data = telemetry-batch-formatted capture, §4) |
| `REBOOT` | — | — *(device reboots after replying)* |
| `ENTER_DFU` | — | — *(device jumps to ROM bootloader after replying)* |
| `HEARTBEAT` | — | `state u8 (DeviceState), fault_active u32` |

Error conventions:

- Unknown `id` → `NACK_BAD_PARAM`; `value` outside `min..max` →
  `NACK_OUT_OF_BOUNDS`; write to `RO` param → `NACK_BAD_PARAM`.
- Command not allowed in the current `DeviceState` (e.g. `PARAM_WRITE` of
  motor params or `MOTOR_ID_START` while `ARMED`/`RUNNING`, `ARM` while
  `FAULT`) → `NACK_BAD_STATE`.
- `PROTECTION_SET` values are bounds-checked against the `prot.*` parameter
  limits (OVP must sit in 63.5–65.5 V, between the 63 V brake target and the
  ~66 V hardware backstop).
- `MOTOR_ID_START` while an identification is already running → `BUSY`.
- Malformed frames never generate a response (they are dropped and counted).

## 4. Telemetry batch layout

Payload of `TELEMETRY_DATA` (and of `SCOPE_READ` capture data):

```
[base_timestamp_us u32][channel_mask u32][n_samples u16][decimation u16]
n_samples × ( [t_offset_us u16][int16 × popcount(channel_mask)] )
```

Channel values are `int16`, physical = raw × `scale` (see
`telemetry.channels`), packed in **ascending bit order** of `channel_mask`.
Sample period = `decimation / fsw_hz`. Implemented by
`build_telemetry` / `parse_telemetry`.

## 5. Safety rules (normative)

- **Heartbeat watchdog:** while `ARMED` or `RUNNING`, the device disarms
  (PWM off), latches `Fault.HEARTBEAT_LOSS`, and enters `FAULT` if no
  `HEARTBEAT` arrives within `heartbeat_timeout_ms` (200 ms). Host sends
  every `heartbeat_period_ms` (50 ms).
- **`STOP` is always honored** in every state: zero setpoint, disarm, PWM off.
- `FAULT_CLEAR` succeeds only when the underlying condition has cleared;
  the device returns to `STANDBY`, never directly to `ARMED`.
- Protocol handling must never run in the control ISR; hardware protection
  (TIM1 BRK, comparators) does not depend on any of this.

## 6. Versioning

- `VER` byte = `meta.version_major`. A receiver drops frames whose major
  version it does not implement (counted, no response).
- Additive, non-breaking changes (new command, new param, new telemetry
  channel, new fault bit) bump `meta.version_minor` only.
