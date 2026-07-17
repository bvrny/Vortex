"""SimDevice: full-protocol device simulator per PROTO-VORTEX-01A/PROTOCOL.md."""

import json
import struct

import pytest

import vortex_protocol as vp
from simulator import SimDevice


def rpc(dev, cmd, payload=b"", seq=1):
    """Send one request, return (status, payload-after-status)."""
    dec = vp.WireDecoder()
    frames = dec.feed(dev.feed(vp.encode_wire(vp.Frame(cmd=cmd, payload=payload, seq=seq))))
    assert len(frames) == 1
    f = frames[0]
    assert f.flags & vp.FLAG_RESPONSE
    assert f.cmd == cmd
    assert f.seq == seq
    return vp.Status(f.payload[0]), f.payload[1:]


def drain(dev, dt, steps=1):
    """Advance sim time, return unsolicited frames."""
    dec = vp.WireDecoder()
    out = []
    for _ in range(steps):
        out += dec.feed(dev.tick(dt))
    return out


def write_param(dev, name, value):
    meta = vp.PARAM_BY_NAME[name]
    payload = struct.pack("<H", meta.id) + vp.encode_param_value(meta, value)
    return rpc(dev, vp.Cmd.PARAM_WRITE, payload)


def read_param(dev, name):
    meta = vp.PARAM_BY_NAME[name]
    status, rest = rpc(dev, vp.Cmd.PARAM_READ, struct.pack("<H", meta.id))
    assert status == vp.Status.OK
    (pid,) = struct.unpack_from("<H", rest, 0)
    assert pid == meta.id
    return vp.decode_param_value(meta, rest[2:])


def arm(dev):
    status, _ = rpc(dev, vp.Cmd.ARM)
    assert status == vp.Status.OK


# ---------------------------------------------------------------- basics


def test_hello_returns_protocol_version():
    status, rest = rpc(dev := SimDevice(), vp.Cmd.HELLO)
    assert status == vp.Status.OK
    assert rest == bytes([vp.PROTOCOL_VERSION_MAJOR, vp.PROTOCOL_VERSION_MINOR])
    assert dev.state == vp.DeviceState.STANDBY


def test_device_info_has_fw_version_uid_and_name():
    status, rest = rpc(SimDevice(), vp.Cmd.DEVICE_INFO)
    assert status == vp.Status.OK
    assert len(rest) >= 15  # 3 version bytes + 12 uid
    assert rest[15:].decode()  # non-empty utf-8 name


def test_unknown_command_nacked():
    status, _ = rpc(SimDevice(), 0x6F)
    assert status == vp.Status.NACK_UNKNOWN_CMD


def test_param_list_returns_all_ids():
    status, rest = rpc(SimDevice(), vp.Cmd.PARAM_LIST)
    assert status == vp.Status.OK
    (count,) = struct.unpack_from("<H", rest, 0)
    ids = struct.unpack_from("<%dH" % count, rest, 2)
    assert set(ids) == set(vp.PARAMS)


# ---------------------------------------------------------------- params


def test_param_read_write_roundtrip():
    dev = SimDevice()
    assert read_param(dev, "motor.pole_pairs") == 7  # default
    status, rest = write_param(dev, "motor.pole_pairs", 4)
    assert status == vp.Status.OK
    assert struct.unpack("<H", rest)[0] == vp.PARAM_BY_NAME["motor.pole_pairs"].id
    assert read_param(dev, "motor.pole_pairs") == 4


def test_param_write_out_of_bounds_nacked():
    dev = SimDevice()
    status, _ = write_param(dev, "prot.overvoltage_v", 66.5)  # above 65.5 max
    assert status == vp.Status.NACK_OUT_OF_BOUNDS
    assert read_param(dev, "prot.overvoltage_v") == pytest.approx(65.0)


def test_param_unknown_id_nacked():
    dev = SimDevice()
    status, _ = rpc(dev, vp.Cmd.PARAM_READ, struct.pack("<H", 0x7FFF))
    assert status == vp.Status.NACK_BAD_PARAM
    status, _ = rpc(dev, vp.Cmd.PARAM_WRITE, struct.pack("<H", 0x7FFF) + b"\x00")
    assert status == vp.Status.NACK_BAD_PARAM


def test_param_default_restores_defaults():
    dev = SimDevice()
    write_param(dev, "motor.pole_pairs", 4)
    status, _ = rpc(dev, vp.Cmd.PARAM_DEFAULT)
    assert status == vp.Status.OK
    assert read_param(dev, "motor.pole_pairs") == 7


def test_param_save_load_roundtrip(tmp_path):
    pf = tmp_path / "params.json"
    dev = SimDevice(param_file=pf)
    write_param(dev, "motor.r_phase", 0.05)
    status, _ = rpc(dev, vp.Cmd.PARAM_SAVE)
    assert status == vp.Status.OK
    write_param(dev, "motor.r_phase", 0.09)
    status, _ = rpc(dev, vp.Cmd.PARAM_LOAD)
    assert status == vp.Status.OK
    assert read_param(dev, "motor.r_phase") == pytest.approx(0.05)
    # A fresh device with the same file boots with saved values.
    dev2 = SimDevice(param_file=pf)
    assert read_param(dev2, "motor.r_phase") == pytest.approx(0.05)


def test_param_load_missing_file_nacked(tmp_path):
    dev = SimDevice(param_file=tmp_path / "none.json")
    status, _ = rpc(dev, vp.Cmd.PARAM_LOAD)
    assert status == vp.Status.NACK_BAD_STATE


def test_param_load_rejects_corrupt_file(tmp_path):
    pf = tmp_path / "params.json"
    dev = SimDevice(param_file=pf)
    rpc(dev, vp.Cmd.PARAM_SAVE)
    blob = json.loads(pf.read_text())
    blob["params"]["0x0001"] = 64  # tamper without fixing crc
    pf.write_text(json.dumps(blob))
    status, _ = rpc(dev, vp.Cmd.PARAM_LOAD)
    assert status == vp.Status.NACK_BAD_STATE
    assert read_param(dev, "motor.pole_pairs") == 7  # untouched


# ---------------------------------------------------------------- arming / heartbeat


def test_arm_and_heartbeat_reports_state_and_faults():
    dev = SimDevice()
    arm(dev)
    assert dev.state == vp.DeviceState.ARMED
    status, rest = rpc(dev, vp.Cmd.HEARTBEAT)
    assert status == vp.Status.OK
    state, faults = struct.unpack("<BI", rest)
    assert state == vp.DeviceState.ARMED
    assert faults == 0


def test_arm_outside_standby_nacked():
    dev = SimDevice()
    arm(dev)
    status, _ = rpc(dev, vp.Cmd.ARM)
    assert status == vp.Status.NACK_BAD_STATE


def test_param_write_while_armed_nacked():
    dev = SimDevice()
    arm(dev)
    status, _ = write_param(dev, "motor.r_phase", 0.05)
    assert status == vp.Status.NACK_BAD_STATE


def test_setpoint_moves_armed_to_running_and_back():
    dev = SimDevice()
    arm(dev)
    sp = struct.pack("<Bf", vp.SetpointMode.TORQUE, 10.0)
    status, _ = rpc(dev, vp.Cmd.SETPOINT, sp)
    assert status == vp.Status.OK
    assert dev.state == vp.DeviceState.RUNNING
    status, _ = rpc(dev, vp.Cmd.SETPOINT, struct.pack("<Bf", vp.SetpointMode.TORQUE, 0.0))
    assert status == vp.Status.OK
    assert dev.state == vp.DeviceState.ARMED


def test_setpoint_in_standby_nacked():
    dev = SimDevice()
    status, _ = rpc(dev, vp.Cmd.SETPOINT, struct.pack("<Bf", vp.SetpointMode.TORQUE, 5.0))
    assert status == vp.Status.NACK_BAD_STATE


def test_stop_always_honored():
    dev = SimDevice()
    arm(dev)
    rpc(dev, vp.Cmd.SETPOINT, struct.pack("<Bf", vp.SetpointMode.SPEED, 1000.0))
    status, _ = rpc(dev, vp.Cmd.STOP)
    assert status == vp.Status.OK
    assert dev.state == vp.DeviceState.STANDBY
    # STOP in FAULT stays in FAULT but still returns OK.
    dev.inject_fault(vp.Fault.OVERCURRENT)
    status, _ = rpc(dev, vp.Cmd.STOP)
    assert status == vp.Status.OK
    assert dev.state == vp.DeviceState.FAULT


def test_heartbeat_timeout_faults_the_drive():
    dev = SimDevice()
    arm(dev)
    drain(dev, 0.1)  # within 200 ms window: still armed
    assert dev.state == vp.DeviceState.ARMED
    rpc(dev, vp.Cmd.HEARTBEAT)  # feeds the watchdog
    drain(dev, 0.15)
    assert dev.state == vp.DeviceState.ARMED
    drain(dev, 0.3)  # blows past the window
    assert dev.state == vp.DeviceState.FAULT
    status, rest = rpc(dev, vp.Cmd.FAULT_READ)
    assert status == vp.Status.OK
    active, latched = struct.unpack("<II", rest)
    assert latched & (1 << vp.Fault.HEARTBEAT_LOSS)


def test_heartbeat_not_required_in_standby():
    dev = SimDevice()
    drain(dev, 10.0)
    assert dev.state == vp.DeviceState.STANDBY


# ---------------------------------------------------------------- faults


def test_fault_injection_while_running_disarms():
    dev = SimDevice()
    arm(dev)
    rpc(dev, vp.Cmd.SETPOINT, struct.pack("<Bf", vp.SetpointMode.TORQUE, 20.0))
    dev.inject_fault(vp.Fault.OVERCURRENT)
    assert dev.state == vp.DeviceState.FAULT
    status, _ = rpc(dev, vp.Cmd.ARM)
    assert status == vp.Status.NACK_BAD_STATE


def test_fault_clear_requires_condition_gone():
    dev = SimDevice()
    dev.inject_fault(vp.Fault.OVERVOLTAGE)
    status, _ = rpc(dev, vp.Cmd.FAULT_CLEAR)
    assert status == vp.Status.NACK_BAD_STATE  # condition still active
    dev.clear_fault_condition(vp.Fault.OVERVOLTAGE)
    status, _ = rpc(dev, vp.Cmd.FAULT_CLEAR)
    assert status == vp.Status.OK
    assert dev.state == vp.DeviceState.STANDBY
    status, rest = rpc(dev, vp.Cmd.FAULT_READ)
    active, latched = struct.unpack("<II", rest)
    assert active == 0 and latched == 0


# ---------------------------------------------------------------- telemetry


def test_telemetry_streams_and_stops():
    dev = SimDevice()
    mask = 0x1C7  # ia ib ic + vbus id iq (default mask)
    status, _ = rpc(dev, vp.Cmd.TELEMETRY_START, struct.pack("<IH", mask, 8))
    assert status == vp.Status.OK
    frames = drain(dev, 0.01, steps=3)
    assert frames and all(f.cmd == vp.Cmd.TELEMETRY_DATA for f in frames)
    assert all(not (f.flags & vp.FLAG_RESPONSE) for f in frames)
    batch = vp.parse_telemetry(frames[0].payload)
    assert batch.channel_mask == mask
    assert batch.decimation == 8
    n = bin(mask).count("1")
    assert all(len(vals) == n for _, vals in batch.samples)
    status, _ = rpc(dev, vp.Cmd.TELEMETRY_STOP)
    assert status == vp.Status.OK
    assert drain(dev, 0.01, steps=3) == []


def test_telemetry_vbus_is_plausible():
    dev = SimDevice()
    mask = 1 << vp.CHANNEL_BY_NAME["vbus"].bit
    rpc(dev, vp.Cmd.TELEMETRY_START, struct.pack("<IH", mask, 8))
    frames = drain(dev, 0.01, steps=2)
    scale = vp.CHANNEL_BY_NAME["vbus"].scale
    for f in frames:
        for _, (raw,) in vp.parse_telemetry(f.payload).samples:
            assert 40.0 < raw * scale < 56.0  # 48 V system at rest


# ---------------------------------------------------------------- motor ID


def test_motor_id_runs_to_done_and_updates_params():
    dev = SimDevice()
    status, _ = rpc(dev, vp.Cmd.MOTOR_ID_START)
    assert status == vp.Status.OK
    frames = []
    for _ in range(100):
        frames += drain(dev, 0.1)
        if frames and frames[-1].payload[0] == vp.MotorIdStage.DONE:
            break
    assert frames, "no MOTOR_ID_PROGRESS frames emitted"
    assert all(f.cmd == vp.Cmd.MOTOR_ID_PROGRESS for f in frames)
    stages = [f.payload[0] for f in frames]
    assert stages[-1] == vp.MotorIdStage.DONE
    assert vp.MotorIdStage.RESISTANCE in stages
    assert vp.MotorIdStage.INDUCTANCE in stages
    stage, pct, r, ld, lq, flux = struct.unpack("<BBffff", frames[-1].payload)
    assert pct == 100
    assert read_param(dev, "motor.r_phase") == pytest.approx(r)
    assert read_param(dev, "motor.l_d") == pytest.approx(ld)
    assert read_param(dev, "motor.l_q") == pytest.approx(lq)
    assert read_param(dev, "motor.flux_lambda") == pytest.approx(flux)
    meta_r = vp.PARAM_BY_NAME["motor.r_phase"]
    assert meta_r.min <= r <= meta_r.max


def test_motor_id_busy_and_bad_state():
    dev = SimDevice()
    rpc(dev, vp.Cmd.MOTOR_ID_START)
    status, _ = rpc(dev, vp.Cmd.MOTOR_ID_START)
    assert status == vp.Status.BUSY
    status, _ = rpc(dev, vp.Cmd.MOTOR_ID_ABORT)
    assert status == vp.Status.OK
    arm(dev)
    status, _ = rpc(dev, vp.Cmd.MOTOR_ID_START)
    assert status == vp.Status.NACK_BAD_STATE


# ---------------------------------------------------------------- scope


def test_scope_capture_roundtrip():
    dev = SimDevice()
    mask = (1 << vp.CHANNEL_BY_NAME["ia"].bit) | (1 << vp.CHANNEL_BY_NAME["vbus"].bit)
    cfg = struct.pack("<IHHBBh", mask, 4, 16, vp.CHANNEL_BY_NAME["ia"].bit,
                      vp.TrigEdge.RISING, 0)
    status, _ = rpc(dev, vp.Cmd.SCOPE_CONFIG, cfg)
    assert status == vp.Status.OK
    status, _ = rpc(dev, vp.Cmd.SCOPE_ARM)
    assert status == vp.Status.OK
    blob = bytearray()
    while True:
        status, rest = rpc(dev, vp.Cmd.SCOPE_READ, struct.pack("<I", len(blob)))
        assert status == vp.Status.OK
        total, offset = struct.unpack_from("<II", rest, 0)
        assert offset == len(blob)
        blob += rest[8:]
        if len(blob) == total:
            break
    batch = vp.parse_telemetry(bytes(blob))
    assert batch.channel_mask == mask
    assert batch.decimation == 4
    assert len(batch.samples) >= 16


def test_scope_read_without_capture_nacked():
    dev = SimDevice()
    status, _ = rpc(dev, vp.Cmd.SCOPE_READ, struct.pack("<I", 0))
    assert status == vp.Status.NACK_BAD_STATE


# ---------------------------------------------------------------- robustness


def test_malformed_payload_nacked_bad_len():
    dev = SimDevice()
    status, _ = rpc(dev, vp.Cmd.PARAM_READ, b"\x01")  # id truncated
    assert status == vp.Status.NACK_BAD_LEN


def test_garbage_bytes_do_not_kill_the_device():
    dev = SimDevice()
    assert dev.feed(bytes(range(1, 50)) + b"\x00") == b""
    status, _ = rpc(dev, vp.Cmd.HELLO)
    assert status == vp.Status.OK
