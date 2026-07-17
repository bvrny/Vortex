"""DeviceLink: transport-agnostic protocol client used by the desktop app."""

import struct

import pytest

import vortex_protocol as vp
from simulator import SimDevice
from vortex_app.link import DeviceLink, LinkTimeout, SimTransport


def make_link():
    dev = SimDevice()
    tr = SimTransport(dev)
    return dev, tr, DeviceLink(tr)


def test_request_matches_response_by_seq():
    _, _, link = make_link()
    status, payload = link.request(vp.Cmd.HELLO)
    assert status == vp.Status.OK
    assert payload == bytes([vp.PROTOCOL_VERSION_MAJOR, vp.PROTOCOL_VERSION_MINOR])
    # seq increments per request and responses still match
    for _ in range(300):  # wraps past 255
        status, _ = link.request(vp.Cmd.HEARTBEAT)
        assert status == vp.Status.OK


def test_param_helpers_roundtrip():
    _, _, link = make_link()
    assert link.read_param("motor.pole_pairs") == 7
    assert link.write_param("motor.pole_pairs", 4) == vp.Status.OK
    assert link.read_param("motor.pole_pairs") == 4
    assert link.write_param("prot.overvoltage_v", 99.0) == vp.Status.NACK_OUT_OF_BOUNDS


def test_unsolicited_frames_delivered_by_poll_not_request():
    dev, tr, link = make_link()
    assert link.request(vp.Cmd.TELEMETRY_START,
                        struct.pack("<IH", 0x1, 8))[0] == vp.Status.OK
    tr.tick(0.01)  # generates TELEMETRY_DATA into the rx stream
    # a request issued now must skip the telemetry frames and find its reply
    status, _ = link.request(vp.Cmd.HEARTBEAT)
    assert status == vp.Status.OK
    frames = link.poll()
    assert frames and all(f.cmd == vp.Cmd.TELEMETRY_DATA for f in frames)


def test_request_timeout_raises():
    class DeadTransport:
        def write(self, data):
            pass

        def read(self):
            return b""

    link = DeviceLink(DeadTransport(), timeout=0.05)
    with pytest.raises(LinkTimeout):
        link.request(vp.Cmd.HELLO)


def test_state_helpers():
    dev, _, link = make_link()
    assert link.request(vp.Cmd.ARM)[0] == vp.Status.OK
    assert dev.state == vp.DeviceState.ARMED
    state, faults = link.heartbeat()
    assert state == vp.DeviceState.ARMED
    assert faults == 0
    assert link.request(vp.Cmd.STOP)[0] == vp.Status.OK
    assert dev.state == vp.DeviceState.STANDBY
