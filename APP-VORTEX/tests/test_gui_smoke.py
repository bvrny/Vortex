"""Offscreen GUI smoke test: connect to sim, arm, stream telemetry, stop."""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

import vortex_protocol as vp                      # noqa: E402
from PySide6.QtWidgets import QApplication        # noqa: E402

from vortex_app import main as app_main           # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_connect_arm_stream_stop(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(app_main, "SIM_PARAM_FILE", tmp_path / "params.json")
    win = app_main.MainWindow()
    win._on_connect()
    assert win.link is not None
    # params were loaded into the tree
    assert win.param_tree.topLevelItemCount() > 0

    win._simple_cmd(vp.Cmd.ARM)
    win._on_heartbeat()
    assert win.state_label.text() == "ARMED"

    # pump the poll path: sim time advances, telemetry lands in the store
    for _ in range(5):
        win._on_poll()
    t, v = win.store.window("vbus")
    assert t.size > 0
    assert 40.0 < v[-1] < 56.0

    win._on_stop()
    win._on_heartbeat()
    assert win.state_label.text() == "STANDBY"

    win._disconnect()
    assert win.link is None
