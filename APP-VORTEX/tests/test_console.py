"""Phase 5: protocol console, command history, event log.

User journeys:
- As a power user, I want a console to type protocol commands (like the
  firmware CLI workflow) with command history, so quick experiments don't
  need mouse trips.
- As a tuner, I want a timestamped event log of state transitions and fault
  changes, so I can reconstruct what happened.
"""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

import vortex_protocol as vp                                  # noqa: E402

from simulator import SimDevice                               # noqa: E402
from vortex_app.link import DeviceLink, SimTransport          # noqa: E402
from vortex_app.widgets.console import (CommandHistory,       # noqa: E402
                                        ConsoleLogic, EventLog)


@pytest.fixture()
def link():
    return DeviceLink(SimTransport(SimDevice()))


@pytest.fixture()
def con(link):
    return ConsoleLogic(lambda: link)


def test_help_lists_commands(con):
    out = con.execute("help")
    for word in ("param", "arm", "stop", "sp", "fault"):
        assert word in out


def test_arm_and_stop(con, link):
    assert "OK" in con.execute("arm")
    assert link.transport.dev.state == vp.DeviceState.ARMED
    assert "OK" in con.execute("stop")
    assert link.transport.dev.state == vp.DeviceState.STANDBY


def test_setpoint_command(con, link):
    con.execute("arm")
    assert "OK" in con.execute("sp torque 5")
    assert link.transport.dev._setpoint == pytest.approx(5.0)


def test_param_read_and_write(con, link):
    out = con.execute("param motor.r_phase")
    assert "0.02" in out
    assert "OK" in con.execute("param motor.pole_pairs 14")
    assert link.read_param("motor.pole_pairs") == 14


def test_fault_read(con):
    out = con.execute("fault")
    assert "active" in out


def test_errors_are_messages_not_exceptions(con):
    assert "unknown" in con.execute("frobnicate").lower()
    assert "usage" in con.execute("sp torque abc").lower()
    assert "unknown param" in con.execute("param nope.nope").lower()


def test_dfu_command(con, link):
    assert "OK" in con.execute("dfu")


def test_command_history_navigation():
    h = CommandHistory()
    h.add("first")
    h.add("second")
    assert h.prev() == "second"
    assert h.prev() == "first"
    assert h.prev() == "first"        # clamped at oldest
    assert h.next() == "second"
    assert h.next() == ""             # back to fresh line


def test_event_log_records_changes_only():
    log = EventLog()
    log.record_state(vp.DeviceState.STANDBY)
    log.record_state(vp.DeviceState.STANDBY)   # no change, no entry
    log.record_state(vp.DeviceState.ARMED)
    assert len(log.entries) == 2
    assert "ARMED" in log.entries[-1][2]

    oc_mask = 1 << vp.Fault.OVERCURRENT         # Fault members are bit indices
    log.record_faults(0)                        # no faults, no entry
    log.record_faults(oc_mask)
    assert len(log.entries) == 3
    assert "OVERCURRENT" in log.entries[-1][2]
    log.record_faults(oc_mask)                  # unchanged, no entry
    assert len(log.entries) == 3
