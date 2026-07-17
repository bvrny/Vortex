"""Wire enums used inside command payloads (defined in protocol.yaml)."""

import vortex_protocol as vp


def test_device_state_enum():
    # Mirrors the firmware fault state machine (CLAUDE.md):
    # init -> precharge -> self-test -> standby -> armed -> running / fault.
    assert vp.DeviceState.INIT == 0
    assert vp.DeviceState.PRECHARGE == 1
    assert vp.DeviceState.SELFTEST == 2
    assert vp.DeviceState.STANDBY == 3
    assert vp.DeviceState.ARMED == 4
    assert vp.DeviceState.RUNNING == 5
    assert vp.DeviceState.FAULT == 6


def test_setpoint_mode_enum():
    assert vp.SetpointMode.TORQUE == 0  # SETPOINT value = iq amps
    assert vp.SetpointMode.SPEED == 1   # SETPOINT value = rpm


def test_motor_id_stage_enum():
    assert vp.MotorIdStage.IDLE == 0
    assert vp.MotorIdStage.RESISTANCE == 1
    assert vp.MotorIdStage.INDUCTANCE == 2
    assert vp.MotorIdStage.FLUX == 3
    assert vp.MotorIdStage.DONE == 4
    assert vp.MotorIdStage.FAILED == 5


def test_trig_edge_enum():
    assert vp.TrigEdge.RISING == 0
    assert vp.TrigEdge.FALLING == 1


def test_fault_bits_unique_and_named():
    # Fault values are BIT POSITIONS in the u32 fault mask of
    # FAULT_READ / HEARTBEAT responses.
    assert vp.Fault.OVERCURRENT == 0
    assert vp.Fault.OVERVOLTAGE == 1
    assert vp.Fault.UNDERVOLTAGE == 2
    assert vp.Fault.HEARTBEAT_LOSS == 7
    bits = [f.value for f in vp.Fault]
    assert len(bits) == len(set(bits))
    assert all(0 <= b < 32 for b in bits)
    for f in vp.Fault:
        assert vp.FAULT_NAMES[f.value] == f.name


def test_decode_faults_returns_names_in_bit_order():
    mask = (1 << vp.Fault.HEARTBEAT_LOSS) | (1 << vp.Fault.OVERCURRENT)
    assert vp.decode_faults(mask) == ["OVERCURRENT", "HEARTBEAT_LOSS"]
    assert vp.decode_faults(0) == []
