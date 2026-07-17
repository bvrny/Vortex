"""Phase 4: scope capture, step response, bandwidth knob, motor-ID wizard.

User journeys:
- As a tuner, I want to capture a triggered high-rate window (scope) and a
  setpoint step response, so I can see and judge the current loop behavior.
- As a tuner, I want one bandwidth knob that recomputes kp/ki from the
  identified R and L, instead of guessing two gains.
- As a user, I want motor identification as a guided flow with results I can
  review.
"""

import os
import struct

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

import vortex_protocol as vp                                  # noqa: E402
from PySide6.QtWidgets import QApplication                    # noqa: E402

from simulator import SimDevice                               # noqa: E402
from vortex_app.link import DeviceLink, SimTransport          # noqa: E402
from vortex_app.widgets.tuning import (BandwidthKnob,         # noqa: E402
                                       MotorIdMonitor,
                                       compute_iloop_gains,
                                       run_step_capture)


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture()
def link():
    return DeviceLink(SimTransport(SimDevice()))


MASK3 = 0x7  # ia ib ic


def test_scope_helpers_chunked_roundtrip(link):
    assert link.scope_config(MASK3, decimation=4) == vp.Status.OK
    assert link.scope_arm() == vp.Status.OK
    status, blob = link.scope_read()
    assert status == vp.Status.OK
    # SimDevice captures 128 samples x 3ch -> >1 chunk; reassembly must be exact
    batch = vp.parse_telemetry(blob)
    assert batch.channel_mask == MASK3
    assert len(batch.samples) == 128


def test_scope_read_without_capture_is_bad_state(link):
    status, blob = link.scope_read()
    assert status == vp.Status.NACK_BAD_STATE
    assert blob is None


def test_compute_iloop_gains_matches_protocol_defaults():
    kp, ki = compute_iloop_gains(0.02, 2e-5, 2666.667)
    assert kp == pytest.approx(0.3351, rel=1e-3)
    assert ki == pytest.approx(335.1, rel=1e-3)


def test_bandwidth_knob_writes_gains(qapp, link):
    knob = BandwidthKnob(lambda: link)
    knob.set_bandwidth(3000.0)
    assert knob.apply() == vp.Status.OK
    r = link.read_param("motor.r_phase")
    l_d = link.read_param("motor.l_d")
    kp, ki = compute_iloop_gains(r, l_d, 3000.0)
    assert link.read_param("iloop.kp") == pytest.approx(kp, rel=1e-5)
    assert link.read_param("iloop.ki") == pytest.approx(ki, rel=1e-5)
    assert link.read_param("iloop.bandwidth_hz") == pytest.approx(3000.0)


def test_run_step_capture_returns_batch(link):
    link.request(vp.Cmd.ARM)
    batch = run_step_capture(link, vp.SetpointMode.TORQUE, 5.0,
                             mask=MASK3, decimation=4)
    assert batch.channel_mask == MASK3
    assert len(batch.samples) > 0
    # step was actually applied
    assert link.transport.dev._setpoint == pytest.approx(5.0)


def test_scope_panel_capture_populates_plot(qapp, link):
    from vortex_app.widgets.scope import ScopePanel
    panel = ScopePanel(lambda: link)
    assert panel.capture(step=False)
    assert panel.last_batch is not None
    assert len(panel.last_batch.samples) == 128
    assert len(panel.plot.listDataItems()) == len(
        vp.active_channels(panel.last_batch.channel_mask))
    # step capture drives the setpoint too
    link.request(vp.Cmd.ARM)
    assert panel.capture(step=True)
    assert link.transport.dev._setpoint == pytest.approx(panel.amp_spin.value())


def test_motor_id_wizard_shows_results(qapp, link):
    from vortex_app.widgets.tuning import MotorIdWizard
    wiz = MotorIdWizard(None, lambda: None)
    done = struct.pack("<BBffff", int(vp.MotorIdStage.DONE), 100,
                       0.0187, 1.55e-5, 1.62e-5, 0.0048)
    wiz.handle_progress(done)
    assert wiz.progress.value() == 100
    assert "0.0187" in wiz.result_label.text()


def test_motor_id_monitor_tracks_progress_frames():
    mon = MotorIdMonitor()
    running = struct.pack("<BBffff", int(vp.MotorIdStage.RESISTANCE), 33,
                          0, 0, 0, 0)
    mon.handle_progress(running)
    assert not mon.done
    assert mon.stage == vp.MotorIdStage.RESISTANCE
    assert mon.percent == 33

    done = struct.pack("<BBffff", int(vp.MotorIdStage.DONE), 100,
                       0.0187, 1.55e-5, 1.62e-5, 0.0048)
    mon.handle_progress(done)
    assert mon.done
    assert mon.results["r_phase"] == pytest.approx(0.0187)
    assert mon.results["flux"] == pytest.approx(0.0048)

    failed = struct.pack("<BBffff", int(vp.MotorIdStage.FAILED), 60, 0, 0, 0, 0)
    mon2 = MotorIdMonitor()
    mon2.handle_progress(failed)
    assert mon2.done and mon2.failed
