"""Live-tuning layout + drive controls.

User journeys:
- As a tuner, I edit parameters WHILE watching the waveforms — params live in
  a permanent side pane, not a separate tab.
- As a driver, I choose rotation direction, and can drive the motor from the
  keyboard: Up/Down nudges the setpoint, Left/Right flips direction,
  Space stops.
- Regression: building a value editor for EVERY parameter must not crash
  (u32 params like telem.default_mask overflow a signed QSpinBox).
"""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

import vortex_protocol as vp                                  # noqa: E402
from PySide6.QtCore import Qt                                 # noqa: E402
from PySide6.QtWidgets import QApplication, QSplitter, QTabWidget  # noqa: E402

from simulator import SimDevice                               # noqa: E402
from vortex_app import main as app_main                       # noqa: E402
from vortex_app.link import DeviceLink, SimTransport          # noqa: E402
from vortex_app.widgets.params import ParamPanel              # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture()
def win(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(app_main, "SIM_PARAM_FILE", tmp_path / "params.json")
    w = app_main.MainWindow()
    w._on_connect()
    yield w
    w._disconnect()


def test_editor_creation_survives_every_param(qapp):
    link = DeviceLink(SimTransport(SimDevice()))
    panel = ParamPanel(lambda: link)
    panel.refresh()
    delegate = panel.tree.itemDelegateForColumn(1)
    for g in range(panel.tree.topLevelItemCount()):
        group = panel.tree.topLevelItem(g)
        for i in range(group.childCount()):
            index = panel.tree.indexFromItem(group.child(i), 1)
            editor = delegate.createEditor(panel.tree, None, index)
            assert editor is not None
    # the u32 mask param keeps its full range
    meta = vp.PARAM_BY_NAME["telem.default_mask"]
    item = panel.tree.findItems("default_mask", Qt.MatchRecursive)[0]
    editor = delegate.createEditor(panel.tree,
                                   None, panel.tree.indexFromItem(item, 1))
    assert editor.maximum() == meta.max


def test_params_beside_waveforms_not_in_tab(qapp):
    w = app_main.MainWindow()
    splitter = w.findChild(QSplitter, "main_splitter")
    assert splitter is not None
    assert splitter.indexOf(w.params_pane) != -1     # params always visible
    tabs = w.findChild(QTabWidget, "main_tabs")
    labels = [tabs.tabText(i) for i in range(tabs.count())]
    assert "Parameters" not in labels
    assert labels[0] == "Dashboard"


def test_direction_control_signs_setpoint(win):
    win._simple_cmd(vp.Cmd.ARM)
    win.sp_spin.setValue(5.0)
    win.dir_combo.setCurrentIndex(1)                  # REV
    win._on_setpoint()
    assert win.link.transport.dev._setpoint == pytest.approx(-5.0)
    win.dir_combo.setCurrentIndex(0)                  # FWD
    win._on_setpoint()
    assert win.link.transport.dev._setpoint == pytest.approx(5.0)


def test_arrow_key_drive(win):
    win._simple_cmd(vp.Cmd.ARM)
    win.kb_drive_btn.setChecked(True)
    win.sp_spin.setValue(0.0)

    assert win._handle_drive_key(Qt.Key_Up)
    assert win.sp_spin.value() == pytest.approx(app_main.TORQUE_STEP_A)
    assert win.link.transport.dev._setpoint == pytest.approx(app_main.TORQUE_STEP_A)

    assert win._handle_drive_key(Qt.Key_Down)
    assert win.sp_spin.value() == pytest.approx(0.0)

    win.sp_spin.setValue(2.0)
    win._handle_drive_key(Qt.Key_Up)
    assert win._handle_drive_key(Qt.Key_Right)        # flip to REV
    assert win.dir_combo.currentIndex() == 1
    assert win.link.transport.dev._setpoint == pytest.approx(
        -(2.0 + app_main.TORQUE_STEP_A))

    # disabled toggle -> keys not consumed, nothing sent
    win.kb_drive_btn.setChecked(False)
    before = win.link.transport.dev._setpoint
    assert not win._handle_drive_key(Qt.Key_Up)
    assert win.link.transport.dev._setpoint == before
