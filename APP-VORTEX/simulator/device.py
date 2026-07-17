"""SimDevice: protocol-complete Vortex device simulator.

Implements PROTO-VORTEX-01A/PROTOCOL.md against the generated
vortex_protocol module. Time is fully simulated: call tick(dt) to advance.
"""

from __future__ import annotations

import json
import math
import struct
from pathlib import Path

import vortex_protocol as vp

FW_VERSION = (0, 1, 0)
UID = bytes(range(12))
DEVICE_NAME = b"Vortex-Sim"

MEASURED_R = 0.0187          # "identified" motor constants, distinct from defaults
MEASURED_LD = 1.55e-5
MEASURED_LQ = 1.62e-5
MEASURED_FLUX = 0.0048
MOTOR_ID_DURATION_S = 2.0

SPEED_TAU_S = 0.2            # first-order mechanical response
RPM_PER_AMP = 20.0           # crude torque-mode speed gain for waveforms
SCOPE_SAMPLES = 128
MAX_CHUNK = vp.MAX_PAYLOAD - 9   # status u8 + total u32 + offset u32

_INT16_MIN, _INT16_MAX = -32768, 32767


def _value_size(meta: vp.ParamMeta) -> int:
    return len(vp.encode_param_value(meta, 0))


class SimDevice:
    def __init__(self, param_file: Path | None = None):
        self.param_file = Path(param_file) if param_file else None
        self.params = {m.id: m.default for m in vp.PARAMS.values()}
        if self.param_file is not None and self.param_file.exists():
            self._load_params()  # corrupt file at boot -> keep defaults
        self.state = vp.DeviceState.STANDBY
        self.t = 0.0
        self.fault_active = 0
        self.fault_latched = 0
        self._last_hb = 0.0
        self._sp_mode = vp.SetpointMode.TORQUE
        self._setpoint = 0.0
        self._speed = 0.0            # rpm
        self._angle = 0.0            # electrical rad
        self._telem_on = False
        self._telem_mask = 0
        self._telem_dec = 8
        self._samp_clock = 0.0       # timestamp of next telemetry sample
        self._samp_carry = 0.0
        self._motor_id_t0 = None     # sim time when ID started, None = idle
        self._scope_cfg = None
        self._scope_blob = None
        self._tx_seq = 0
        self._dec = vp.WireDecoder()

    # ------------------------------------------------------------- wire I/O

    def feed(self, data: bytes) -> bytes:
        """Feed host->device bytes; returns response wire bytes."""
        out = bytearray()
        for frame in self._dec.feed(data):
            out += self._dispatch(frame)
        return bytes(out)

    def tick(self, dt: float) -> bytes:
        """Advance simulated time; returns unsolicited device->host bytes."""
        self.t += dt
        self._update_motion(dt)
        out = bytearray()
        if self.state in (vp.DeviceState.ARMED, vp.DeviceState.RUNNING) and \
                self.t - self._last_hb > vp.HEARTBEAT_TIMEOUT_MS / 1000.0:
            self._trip(vp.Fault.HEARTBEAT_LOSS, transient=True)
        out += self._motor_id_tick()
        out += self._telemetry_tick(dt)
        return bytes(out)

    # ------------------------------------------------------- python-side API

    def inject_fault(self, bit: int) -> None:
        """Test hook: assert a hardware fault condition (stays active)."""
        self.fault_active |= 1 << bit
        self._trip(bit)

    def clear_fault_condition(self, bit: int) -> None:
        """Test hook: the underlying condition goes away (latch remains)."""
        self.fault_active &= ~(1 << bit)

    # ------------------------------------------------------------ dispatch

    def _dispatch(self, f: vp.Frame) -> bytes:
        handler = {
            vp.Cmd.HELLO: self._cmd_hello,
            vp.Cmd.DEVICE_INFO: self._cmd_device_info,
            vp.Cmd.PARAM_LIST: self._cmd_param_list,
            vp.Cmd.PARAM_READ: self._cmd_param_read,
            vp.Cmd.PARAM_WRITE: self._cmd_param_write,
            vp.Cmd.PARAM_SAVE: self._cmd_param_save,
            vp.Cmd.PARAM_LOAD: self._cmd_param_load,
            vp.Cmd.PARAM_DEFAULT: self._cmd_param_default,
            vp.Cmd.TELEMETRY_START: self._cmd_telemetry_start,
            vp.Cmd.TELEMETRY_STOP: self._cmd_telemetry_stop,
            vp.Cmd.MOTOR_ID_START: self._cmd_motor_id_start,
            vp.Cmd.MOTOR_ID_ABORT: self._cmd_motor_id_abort,
            vp.Cmd.PROTECTION_SET: self._cmd_protection_set,
            vp.Cmd.FAULT_READ: self._cmd_fault_read,
            vp.Cmd.FAULT_CLEAR: self._cmd_fault_clear,
            vp.Cmd.ARM: self._cmd_arm,
            vp.Cmd.DISARM: self._cmd_disarm,
            vp.Cmd.STOP: self._cmd_stop,
            vp.Cmd.SETPOINT: self._cmd_setpoint,
            vp.Cmd.SCOPE_CONFIG: self._cmd_scope_config,
            vp.Cmd.SCOPE_ARM: self._cmd_scope_arm,
            vp.Cmd.SCOPE_READ: self._cmd_scope_read,
            vp.Cmd.REBOOT: self._cmd_reboot,
            vp.Cmd.ENTER_DFU: self._cmd_ok,
            vp.Cmd.HEARTBEAT: self._cmd_heartbeat,
        }.get(f.cmd)
        if handler is None:
            return self._reply(f, vp.Status.NACK_UNKNOWN_CMD)
        return handler(f)

    def _reply(self, f: vp.Frame, status: vp.Status, extra: bytes = b"") -> bytes:
        payload = bytes([status]) + (extra if status == vp.Status.OK else b"")
        return vp.encode_wire(vp.Frame(cmd=int(f.cmd), payload=payload, seq=f.seq,
                                       flags=vp.FLAG_RESPONSE))

    def _emit(self, cmd: vp.Cmd, payload: bytes) -> bytes:
        self._tx_seq = (self._tx_seq + 1) & 0xFF
        return vp.encode_wire(vp.Frame(cmd=int(cmd), payload=payload, seq=self._tx_seq))

    # ------------------------------------------------------------ commands

    def _cmd_hello(self, f):
        return self._reply(f, vp.Status.OK,
                           bytes([vp.PROTOCOL_VERSION_MAJOR, vp.PROTOCOL_VERSION_MINOR]))

    def _cmd_device_info(self, f):
        return self._reply(f, vp.Status.OK, bytes(FW_VERSION) + UID + DEVICE_NAME)

    def _cmd_ok(self, f):
        return self._reply(f, vp.Status.OK)

    def _cmd_param_list(self, f):
        ids = sorted(vp.PARAMS)
        return self._reply(f, vp.Status.OK,
                           struct.pack("<H%dH" % len(ids), len(ids), *ids))

    def _cmd_param_read(self, f):
        if len(f.payload) != 2:
            return self._reply(f, vp.Status.NACK_BAD_LEN)
        (pid,) = struct.unpack("<H", f.payload)
        meta = vp.PARAMS.get(pid)
        if meta is None:
            return self._reply(f, vp.Status.NACK_BAD_PARAM)
        return self._reply(f, vp.Status.OK, struct.pack("<H", pid) +
                           vp.encode_param_value(meta, self.params[pid]))

    def _cmd_param_write(self, f):
        if len(f.payload) < 2:
            return self._reply(f, vp.Status.NACK_BAD_LEN)
        (pid,) = struct.unpack_from("<H", f.payload, 0)
        meta = vp.PARAMS.get(pid)
        if meta is None or meta.access != "RW":
            return self._reply(f, vp.Status.NACK_BAD_PARAM)
        if self.state in (vp.DeviceState.ARMED, vp.DeviceState.RUNNING):
            return self._reply(f, vp.Status.NACK_BAD_STATE)
        if len(f.payload) != 2 + _value_size(meta):
            return self._reply(f, vp.Status.NACK_BAD_LEN)
        value = vp.decode_param_value(meta, f.payload[2:])
        if not meta.min <= value <= meta.max:
            return self._reply(f, vp.Status.NACK_OUT_OF_BOUNDS)
        self.params[pid] = value
        return self._reply(f, vp.Status.OK, struct.pack("<H", pid))

    def _cmd_param_save(self, f):
        if self.param_file is None:
            return self._reply(f, vp.Status.NACK_BAD_STATE)
        nv = {f"0x{pid:04X}": self.params[pid]
              for pid, m in vp.PARAMS.items() if m.storage == "NV"}
        blob = {"crc": self._params_crc(nv), "params": nv}
        self.param_file.write_text(json.dumps(blob, sort_keys=True))
        return self._reply(f, vp.Status.OK)

    def _cmd_param_load(self, f):
        return self._reply(f, vp.Status.OK if self._load_params()
                           else vp.Status.NACK_BAD_STATE)

    def _cmd_param_default(self, f):
        if self.state in (vp.DeviceState.ARMED, vp.DeviceState.RUNNING):
            return self._reply(f, vp.Status.NACK_BAD_STATE)
        self.params = {m.id: m.default for m in vp.PARAMS.values()}
        return self._reply(f, vp.Status.OK)

    def _cmd_telemetry_start(self, f):
        if len(f.payload) != 6:
            return self._reply(f, vp.Status.NACK_BAD_LEN)
        self._telem_mask, self._telem_dec = struct.unpack("<IH", f.payload)
        if self._telem_dec < 1 or self._telem_mask == 0:
            return self._reply(f, vp.Status.NACK_OUT_OF_BOUNDS)
        self._telem_on = True
        self._samp_clock = self.t
        self._samp_carry = 0.0
        return self._reply(f, vp.Status.OK)

    def _cmd_telemetry_stop(self, f):
        self._telem_on = False
        return self._reply(f, vp.Status.OK)

    def _cmd_motor_id_start(self, f):
        if self._motor_id_t0 is not None:
            return self._reply(f, vp.Status.BUSY)
        if self.state != vp.DeviceState.STANDBY:
            return self._reply(f, vp.Status.NACK_BAD_STATE)
        self._motor_id_t0 = self.t
        return self._reply(f, vp.Status.OK)

    def _cmd_motor_id_abort(self, f):
        self._motor_id_t0 = None
        return self._reply(f, vp.Status.OK)

    def _cmd_protection_set(self, f):
        if len(f.payload) != 8:
            return self._reply(f, vp.Status.NACK_BAD_LEN)
        oc, ov = struct.unpack("<ff", f.payload)
        oc_m = vp.PARAM_BY_NAME["prot.overcurrent_a"]
        ov_m = vp.PARAM_BY_NAME["prot.overvoltage_v"]
        if not (oc_m.min <= oc <= oc_m.max and ov_m.min <= ov <= ov_m.max):
            return self._reply(f, vp.Status.NACK_OUT_OF_BOUNDS)
        self.params[oc_m.id], self.params[ov_m.id] = oc, ov
        return self._reply(f, vp.Status.OK)

    def _cmd_fault_read(self, f):
        return self._reply(f, vp.Status.OK,
                           struct.pack("<II", self.fault_active, self.fault_latched))

    def _cmd_fault_clear(self, f):
        if self.fault_active:
            return self._reply(f, vp.Status.NACK_BAD_STATE)
        self.fault_latched = 0
        if self.state == vp.DeviceState.FAULT:
            self.state = vp.DeviceState.STANDBY
        return self._reply(f, vp.Status.OK)

    def _cmd_arm(self, f):
        if self._motor_id_t0 is not None:
            return self._reply(f, vp.Status.BUSY)
        if self.state != vp.DeviceState.STANDBY:
            return self._reply(f, vp.Status.NACK_BAD_STATE)
        self.state = vp.DeviceState.ARMED
        self._last_hb = self.t
        return self._reply(f, vp.Status.OK)

    def _cmd_disarm(self, f):
        if self.state in (vp.DeviceState.ARMED, vp.DeviceState.RUNNING):
            self.state = vp.DeviceState.STANDBY
        self._setpoint = 0.0
        return self._reply(f, vp.Status.OK)

    def _cmd_stop(self, f):
        # Always honored: zero setpoint + disarm; FAULT stays FAULT.
        self._setpoint = 0.0
        if self.state in (vp.DeviceState.ARMED, vp.DeviceState.RUNNING):
            self.state = vp.DeviceState.STANDBY
        return self._reply(f, vp.Status.OK)

    def _cmd_setpoint(self, f):
        if len(f.payload) != 5:
            return self._reply(f, vp.Status.NACK_BAD_LEN)
        mode, value = struct.unpack("<Bf", f.payload)
        if mode not in (vp.SetpointMode.TORQUE, vp.SetpointMode.SPEED):
            return self._reply(f, vp.Status.NACK_BAD_PARAM)
        if self.state not in (vp.DeviceState.ARMED, vp.DeviceState.RUNNING):
            return self._reply(f, vp.Status.NACK_BAD_STATE)
        self._sp_mode = vp.SetpointMode(mode)
        self._setpoint = value
        self.state = vp.DeviceState.RUNNING if value != 0.0 else vp.DeviceState.ARMED
        return self._reply(f, vp.Status.OK)

    def _cmd_scope_config(self, f):
        if len(f.payload) != 12:
            return self._reply(f, vp.Status.NACK_BAD_LEN)
        mask, dec, pretrig, ch, edge, level = struct.unpack("<IHHBBh", f.payload)
        if mask == 0 or dec < 1:
            return self._reply(f, vp.Status.NACK_OUT_OF_BOUNDS)
        self._scope_cfg = (mask, dec, pretrig, ch, edge, level)
        return self._reply(f, vp.Status.OK)

    def _cmd_scope_arm(self, f):
        if self._scope_cfg is None:
            return self._reply(f, vp.Status.NACK_BAD_STATE)
        # ponytail: trigger condition ignored, capture fires immediately;
        # add real edge triggering when the app's scope UI needs it.
        mask, dec, _pretrig, _ch, _edge, _level = self._scope_cfg
        period_us = dec / vp.FSW_HZ * 1e6
        samples = [(int(i * period_us), self._sample_raw(mask, self.t + i * period_us / 1e6))
                   for i in range(SCOPE_SAMPLES)]
        self._scope_blob = vp.build_telemetry(int(self.t * 1e6) & 0xFFFFFFFF,
                                              mask, dec, samples)
        return self._reply(f, vp.Status.OK)

    def _cmd_scope_read(self, f):
        if self._scope_blob is None:
            return self._reply(f, vp.Status.NACK_BAD_STATE)
        if len(f.payload) != 4:
            return self._reply(f, vp.Status.NACK_BAD_LEN)
        (offset,) = struct.unpack("<I", f.payload)
        if offset > len(self._scope_blob):
            return self._reply(f, vp.Status.NACK_OUT_OF_BOUNDS)
        chunk = self._scope_blob[offset:offset + MAX_CHUNK]
        return self._reply(f, vp.Status.OK,
                           struct.pack("<II", len(self._scope_blob), offset) + chunk)

    def _cmd_reboot(self, f):
        resp = self._reply(f, vp.Status.OK)
        self.__init__(param_file=self.param_file)
        return resp

    def _cmd_heartbeat(self, f):
        self._last_hb = self.t
        return self._reply(f, vp.Status.OK,
                           struct.pack("<BI", int(self.state), self.fault_active))

    # ------------------------------------------------------------ internals

    def _trip(self, bit: int, transient: bool = False) -> None:
        """Latch a fault and drop to FAULT (PWM off, setpoint zeroed)."""
        self.fault_latched |= 1 << bit
        if not transient:
            self.fault_active |= 1 << bit
        self._setpoint = 0.0
        self.state = vp.DeviceState.FAULT

    def _params_crc(self, nv: dict) -> int:
        return vp.crc16(json.dumps(nv, sort_keys=True).encode())

    def _load_params(self) -> bool:
        if self.param_file is None or not self.param_file.exists():
            return False
        try:
            blob = json.loads(self.param_file.read_text())
            nv = blob["params"]
            if blob["crc"] != self._params_crc(nv):
                return False
            loaded = {int(k, 16): v for k, v in nv.items()}
        except (ValueError, KeyError, TypeError):
            return False
        for pid, value in loaded.items():
            if pid in self.params:
                self.params[pid] = value
        return True

    def _update_motion(self, dt: float) -> None:
        if self.state == vp.DeviceState.RUNNING:
            target = (self._setpoint if self._sp_mode == vp.SetpointMode.SPEED
                      else self._setpoint * RPM_PER_AMP)
        else:
            target = 0.0
        self._speed += (target - self._speed) * min(1.0, dt / SPEED_TAU_S)
        pole_pairs = self.params[vp.PARAM_BY_NAME["motor.pole_pairs"].id]
        w_e = self._speed / 60.0 * 2.0 * math.pi * pole_pairs
        self._angle = (self._angle + w_e * dt) % (2.0 * math.pi)

    def _channel_values(self, ts: float) -> dict:
        """Physical value of every telemetry channel at sim time ts."""
        iq = self._setpoint if (self.state == vp.DeviceState.RUNNING and
                                self._sp_mode == vp.SetpointMode.TORQUE) else \
            0.05 * (0.0 if self.state != vp.DeviceState.RUNNING
                    else self._setpoint - self._speed)
        amp = abs(iq)
        th = self._angle + 2.0 * math.pi * 5.0 * (ts - self.t)  # extrapolate a bit
        vbus = min(48.0 + 0.2 * math.sin(2.0 * math.pi * 100.0 * ts),
                   vp.BRAKE_TARGET_V)  # chopper clamps at 63 V
        vamp = 0.05 * vbus
        return {
            "ia": amp * math.sin(th),
            "ib": amp * math.sin(th - 2.0 * math.pi / 3.0),
            "ic": amp * math.sin(th + 2.0 * math.pi / 3.0),
            "va": vamp * math.sin(th), "vb": vamp * math.sin(th - 2.0 * math.pi / 3.0),
            "vc": vamp * math.sin(th + 2.0 * math.pi / 3.0),
            "vbus": vbus, "id": 0.0, "iq": iq,
            "vd": 0.1 * vamp, "vq": vamp, "angle_elec": th % (2.0 * math.pi),
            "speed": self._speed, "iq_setpoint": self._setpoint,
            "temp_inv1": 25.0 + 0.01 * ts, "temp_inv2": 25.2 + 0.01 * ts,
            "temp_inv3": 24.8 + 0.01 * ts, "temp_motor": 25.0 + 0.02 * ts,
        }

    def _sample_raw(self, mask: int, ts: float) -> tuple:
        phys = self._channel_values(ts)
        raw = []
        for ch in vp.active_channels(mask):
            raw.append(max(_INT16_MIN, min(_INT16_MAX,
                                           int(round(phys[ch.name] / ch.scale)))))
        return tuple(raw)

    def _telemetry_tick(self, dt: float) -> bytes:
        if not self._telem_on:
            return b""
        period = self._telem_dec / vp.FSW_HZ
        n_f = self._samp_carry + dt / period
        n = int(n_f)
        self._samp_carry = n_f - n
        if n == 0:
            return b""
        nch = bin(self._telem_mask).count("1")
        per_batch = min((vp.MAX_PAYLOAD - 12) // (2 + 2 * nch),
                        int(0.065 / period) or 1)  # keep u16 t_offset in range
        out = bytearray()
        while n > 0:
            take = min(n, per_batch)
            base = self._samp_clock
            samples = [(int(i * period * 1e6),
                        self._sample_raw(self._telem_mask, base + i * period))
                       for i in range(take)]
            out += self._emit(vp.Cmd.TELEMETRY_DATA,
                              vp.build_telemetry(int(base * 1e6) & 0xFFFFFFFF,
                                                 self._telem_mask, self._telem_dec,
                                                 samples))
            self._samp_clock = base + take * period
            n -= take
        return bytes(out)

    def _motor_id_tick(self) -> bytes:
        if self._motor_id_t0 is None:
            return b""
        p = (self.t - self._motor_id_t0) / MOTOR_ID_DURATION_S
        if p >= 1.0:
            self._motor_id_t0 = None
            for name, val in (("motor.r_phase", MEASURED_R), ("motor.l_d", MEASURED_LD),
                              ("motor.l_q", MEASURED_LQ), ("motor.flux_lambda", MEASURED_FLUX)):
                self.params[vp.PARAM_BY_NAME[name].id] = val
            payload = struct.pack("<BBffff", int(vp.MotorIdStage.DONE), 100,
                                  MEASURED_R, MEASURED_LD, MEASURED_LQ, MEASURED_FLUX)
        else:
            stage = (vp.MotorIdStage.RESISTANCE if p < 1 / 3 else
                     vp.MotorIdStage.INDUCTANCE if p < 2 / 3 else vp.MotorIdStage.FLUX)
            payload = struct.pack("<BBffff", int(stage), int(p * 100), 0, 0, 0, 0)
        return self._emit(vp.Cmd.MOTOR_ID_PROGRESS, payload)
