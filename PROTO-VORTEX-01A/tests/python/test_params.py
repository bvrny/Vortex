"""Parameter metadata generated from protocol.yaml, plus value encoding."""

import struct

import pytest

import vortex_protocol as vp


def test_param_ids_unique_and_metadata_complete():
    ids = [m.id for m in vp.PARAMS.values()]
    assert len(ids) == len(set(ids))
    for meta in vp.PARAMS.values():
        assert meta.name
        assert meta.unit is not None
        assert meta.group
        assert meta.access in ("RO", "RW")
        assert meta.storage in ("RAM", "NV")
        if meta.type != vp.ParamType.ENUM:
            assert meta.min <= meta.default <= meta.max, meta.name


def test_param_lookup_by_name_matches_by_id():
    for meta in vp.PARAMS.values():
        assert vp.PARAM_BY_NAME[meta.name] is meta


def test_key_params_exist_with_expected_types():
    assert vp.PARAM_BY_NAME["motor.pole_pairs"].type == vp.ParamType.U8
    assert vp.PARAM_BY_NAME["motor.r_phase"].type == vp.ParamType.F32
    assert vp.PARAM_BY_NAME["motor.l_d"].type == vp.ParamType.F32
    assert vp.PARAM_BY_NAME["motor.l_q"].type == vp.ParamType.F32
    assert vp.PARAM_BY_NAME["motor.flux_lambda"].type == vp.ParamType.F32
    assert vp.PARAM_BY_NAME["iloop.kp"].type == vp.ParamType.F32
    assert vp.PARAM_BY_NAME["iloop.ki"].type == vp.ParamType.F32
    assert vp.PARAM_BY_NAME["sensor.mode"].type == vp.ParamType.ENUM


def test_current_loop_bandwidth_bounds_track_fsw():
    # fsw = 40 kHz; allowed bandwidth fsw/20 .. fsw/10 = 2..4 kHz,
    # default fsw/15 ≈ 2.667 kHz.
    bw = vp.PARAM_BY_NAME["iloop.bandwidth_hz"]
    assert bw.min == pytest.approx(2000.0)
    assert bw.max == pytest.approx(4000.0)
    assert bw.default == pytest.approx(40000.0 / 15.0, rel=1e-3)


def test_protection_ovp_bounds_respect_hardware_backstop():
    # SAFETY-CRITICAL contract: OVP trip must stay above the 63 V brake
    # target and below the ~66 V hardware comparator backstop.
    ovp = vp.PARAM_BY_NAME["prot.overvoltage_v"]
    assert ovp.min >= 63.0
    assert ovp.max < 66.0


def test_protection_ocp_bounds():
    ocp = vp.PARAM_BY_NAME["prot.overcurrent_a"]
    assert ocp.max <= 180.0  # ~175 A peak phase design target
    assert ocp.min > 0


def test_param_value_roundtrip_f32():
    meta = vp.PARAM_BY_NAME["motor.r_phase"]
    raw = vp.encode_param_value(meta, 0.0123)
    assert len(raw) == 4
    assert vp.decode_param_value(meta, raw) == pytest.approx(0.0123)
    assert raw == struct.pack("<f", 0.0123)  # little-endian IEEE-754


def test_param_value_roundtrip_u8_and_i32():
    pp = vp.PARAM_BY_NAME["motor.pole_pairs"]
    assert vp.decode_param_value(pp, vp.encode_param_value(pp, 7)) == 7
    cpr = vp.PARAM_BY_NAME["sensor.enc_cpr"]
    raw = vp.encode_param_value(cpr, 4096)
    assert len(raw) == 4
    assert vp.decode_param_value(cpr, raw) == 4096


def test_sensor_mode_enum_values():
    mode = vp.PARAM_BY_NAME["sensor.mode"]
    assert mode.enum_values == ("hall", "encoder", "sensorless")
    assert mode.default == 0  # Hall is the current target


def test_telemetry_channels_have_unique_bits_and_scales():
    bits = [c.bit for c in vp.CHANNELS]
    assert len(bits) == len(set(bits))
    names = {c.name for c in vp.CHANNELS}
    for required in ("ia", "ib", "ic", "va", "vb", "vc", "vbus", "id", "iq",
                     "vd", "vq", "angle_elec", "speed", "iq_setpoint"):
        assert required in names, required
    for c in vp.CHANNELS:
        assert c.scale > 0
        assert c.unit is not None


def test_vbus_channel_scale_covers_70v_survival_rating():
    vbus = next(c for c in vp.CHANNELS if c.name == "vbus")
    assert vbus.scale * 32767 >= 70.0  # int16 full scale must represent 70 V


def test_current_channel_scale_covers_peak_current():
    ia = next(c for c in vp.CHANNELS if c.name == "ia")
    assert ia.scale * 32767 >= 175.0  # peak phase current design target
