"""Vortex control app main window.

Thin GUI over DeviceLink + TelemetryStore. Runs against the in-process
simulator or a serial port (real hardware / `python -m simulator` pty).
"""

from __future__ import annotations

import struct
import time
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (QApplication, QComboBox, QDoubleSpinBox,
                               QFileDialog, QHBoxLayout, QLabel, QMainWindow,
                               QMessageBox, QPushButton, QSplitter,
                               QTabWidget, QVBoxLayout, QWidget)

import vortex_protocol as vp
from simulator import SimDevice
from vortex_app import theme
from vortex_app.csvlog import CsvLogger
from vortex_app.link import (DeviceLink, LinkTimeout, SerialTransport,
                             SimTransport, list_serial_ports)
from vortex_app.rings import TelemetryStore
from vortex_app.widgets.console import ConsolePanel
from vortex_app.widgets.dashboard import StatTiles
from vortex_app.widgets.params import ParamPanel
from vortex_app.widgets.plots import ChannelPanel, LivePlots
from vortex_app.widgets.scope import ScopePanel
from vortex_app.widgets.tuning import BandwidthKnob, MotorIdWizard

POLL_MS = 30
PLOT_POINTS = 2000
TORQUE_STEP_A = 0.5      # arrow-key nudge in torque mode
SPEED_STEP_RPM = 100.0   # arrow-key nudge in speed mode
DEFAULT_MASK = 0x1C7 | (1 << 12)  # ia ib ic vbus id iq + speed
DEFAULT_DECIMATION = 8
SIM_PARAM_FILE = Path.home() / ".vortex_sim_params.json"

STATE_COLORS = {
    vp.DeviceState.STANDBY: "#808080",
    vp.DeviceState.ARMED: "#c8a000",
    vp.DeviceState.RUNNING: "#00a000",
    vp.DeviceState.FAULT: "#c80000",
}


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Vortex Control")
        self.resize(1200, 800)
        self.link: DeviceLink | None = None
        self.store = TelemetryStore()
        self._last_tick = time.monotonic()
        self._build_ui()
        self.poll_timer = QTimer(self, interval=POLL_MS, timeout=self._on_poll)
        self.hb_timer = QTimer(self, interval=vp.HEARTBEAT_PERIOD_MS,
                               timeout=self._on_heartbeat)
        QShortcut(QKeySequence(Qt.Key_Space), self, self._on_stop)

    # ---------------------------------------------------------------- UI

    def _build_ui(self):
        self._build_toolbar()
        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.addWidget(self._build_status_strip(), 0)
        # params stay visible beside the waveforms: tune while watching
        split = QSplitter(Qt.Horizontal, objectName="main_splitter")
        self.params_pane = self._build_params_pane()
        split.addWidget(self.params_pane)
        self.tabs = QTabWidget(objectName="main_tabs")
        self.tabs.addTab(self._build_dashboard_tab(), "Dashboard")
        self.tabs.addTab(self._build_tuning_tab(), "Tuning")
        self.console = ConsolePanel(lambda: self.link)
        self.tabs.addTab(self.console, "Console")
        split.addWidget(self.tabs)
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)
        split.setSizes([340, 900])
        layout.addWidget(split, 1)
        self.setCentralWidget(root)

    def _build_toolbar(self):
        tb = self.addToolBar("main")
        tb.setMovable(False)
        self.port_combo = QComboBox()
        self.port_combo.addItems(["In-process simulator", "Serial port:"])
        self.port_edit = QComboBox(editable=True)
        self.port_edit.addItems(list_serial_ports() or ["/dev/ttyACM0"])
        self.port_edit.setMinimumWidth(160)
        self.connect_btn = QPushButton("Connect")
        self.connect_btn.clicked.connect(self._on_connect)
        self.arm_btn = QPushButton("ARM")
        self.arm_btn.clicked.connect(lambda: self._simple_cmd(vp.Cmd.ARM))
        self.disarm_btn = QPushButton("DISARM")
        self.disarm_btn.clicked.connect(lambda: self._simple_cmd(vp.Cmd.DISARM))
        self.stop_btn = QPushButton("STOP (Space)")
        self.stop_btn.setStyleSheet("background:#c80000;color:white;font-weight:bold")
        self.stop_btn.clicked.connect(self._on_stop)
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["Torque (A)", "Speed (rpm)"])
        self.dir_combo = QComboBox()
        self.dir_combo.addItems(["FWD", "REV"])
        self.sp_spin = QDoubleSpinBox(minimum=0, maximum=30000, decimals=2)
        self.apply_btn = QPushButton("Set")
        self.apply_btn.clicked.connect(self._on_setpoint)
        self.kb_drive_btn = QPushButton("Keys: ↑↓ setpoint  ←→ dir",
                                        checkable=True)
        self.kb_drive_btn.setToolTip(
            "Drive from the keyboard: Up/Down nudge the setpoint, "
            "Left/Right flip direction, Space = STOP")
        for w in (self.port_combo, self.port_edit, self.connect_btn, self.arm_btn,
                  self.disarm_btn, self.stop_btn, self.mode_combo, self.dir_combo,
                  self.sp_spin, self.apply_btn, self.kb_drive_btn):
            tb.addWidget(w)

    def _build_status_strip(self):
        strip = QWidget()
        row = QHBoxLayout(strip)
        row.setContentsMargins(4, 2, 4, 2)
        self.state_label = QLabel("DISCONNECTED")
        self.state_label.setStyleSheet("font-size:18px;font-weight:bold")
        self.fault_label = QLabel("")
        self.fault_label.setStyleSheet(f"color:{theme.DANGER}")
        self.fault_label.setWordWrap(True)
        clear_btn = QPushButton("Clear faults")
        clear_btn.clicked.connect(lambda: self._simple_cmd(vp.Cmd.FAULT_CLEAR))
        row.addWidget(self.state_label, 0)
        row.addWidget(self.fault_label, 1)
        row.addWidget(clear_btn, 0)
        return strip

    def _build_dashboard_tab(self):
        tab = QWidget()
        layout = QHBoxLayout(tab)
        left = QVBoxLayout()
        self.tiles = StatTiles()
        self.channel_panel = ChannelPanel()
        self.channel_panel.set_mask(DEFAULT_MASK)
        self.channel_panel.mask_changed.connect(self._on_mask_changed)
        row = QHBoxLayout()
        self.pause_btn = QPushButton("Pause", checkable=True)
        self.pause_btn.toggled.connect(
            lambda on: setattr(self.plots, "paused", on))
        self.record_btn = QPushButton("Record CSV", checkable=True)
        self.record_btn.toggled.connect(self._on_record_toggled)
        row.addWidget(self.pause_btn)
        row.addWidget(self.record_btn)
        left.addWidget(self.tiles, 0)
        left.addWidget(self.channel_panel, 1)
        left.addLayout(row)

        self.plots = LivePlots(PLOT_POINTS)
        self.plots.rebuild(DEFAULT_MASK)
        self.csv_logger = None
        layout.addLayout(left, 0)
        layout.addWidget(self.plots, 1)
        return tab

    def _build_tuning_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        top = QHBoxLayout()
        self.bw_knob = BandwidthKnob(lambda: self.link)
        self.motorid_wiz_btn = QPushButton("Motor identification…")
        self.motorid_wiz_btn.clicked.connect(self._on_motor_id_wizard)
        top.addWidget(self.bw_knob, 1)
        top.addWidget(self.motorid_wiz_btn, 0, Qt.AlignTop)
        layout.addLayout(top, 0)
        self.scope_panel = ScopePanel(lambda: self.link)
        layout.addWidget(self.scope_panel, 1)
        self.motorid_wizard = None
        return tab

    def _on_motor_id_wizard(self):
        self.motorid_wizard = MotorIdWizard(
            self, lambda: self._simple_cmd(vp.Cmd.MOTOR_ID_START))
        self.motorid_wizard.show()

    def _on_mask_changed(self, mask):
        self.plots.rebuild(mask)
        if self.link is None:
            return
        try:
            self.link.request(vp.Cmd.TELEMETRY_STOP)
            if mask:
                self.link.request(vp.Cmd.TELEMETRY_START,
                                  struct.pack("<IH", mask, DEFAULT_DECIMATION))
        except LinkTimeout as e:
            self.statusBar().showMessage(str(e), 4000)

    def _on_record_toggled(self, on):
        if on:
            path, _ = QFileDialog.getSaveFileName(
                self, "Record telemetry CSV", "vortex_log.csv", "CSV (*.csv)")
            if not path:
                self.record_btn.setChecked(False)
                return
            self.csv_logger = CsvLogger(path, self.channel_panel.mask())
        elif self.csv_logger is not None:
            self.csv_logger.close()
            self.csv_logger = None

    def _build_params_pane(self):
        tab = QWidget()
        panel = QVBoxLayout(tab)
        self.params_panel = ParamPanel(lambda: self.link)
        self.params_panel.status_message.connect(
            lambda msg: self.statusBar().showMessage(msg, 4000))
        self.param_tree = self.params_panel.tree      # smoke-test-pinned alias
        panel.addWidget(self.params_panel, 1)

        row = QHBoxLayout()
        self.save_btn = QPushButton("Save to flash")
        self.save_btn.clicked.connect(self._on_save_to_flash)
        row.addWidget(self.save_btn)
        for label, cmd in (("Load", vp.Cmd.PARAM_LOAD),
                           ("Defaults", vp.Cmd.PARAM_DEFAULT)):
            b = QPushButton(label)
            b.clicked.connect(lambda _=False, c=cmd: (self._simple_cmd(c),
                                                      self._refresh_params()))
            row.addWidget(b)
        self.params_panel.save_dirty_changed.connect(self._on_save_dirty)
        panel.addLayout(row)
        return tab

    def _on_save_to_flash(self):
        self._simple_cmd(vp.Cmd.PARAM_SAVE)
        self.params_panel.mark_saved()

    def _on_save_dirty(self, dirty: bool):
        self.save_btn.setStyleSheet(
            f"background:{theme.WARN};color:#10131a;font-weight:bold"
            if dirty else "")

    # ------------------------------------------------------------ actions

    def _on_connect(self):
        if self.link is not None:
            self._disconnect()
            return
        try:
            if self.port_combo.currentIndex() == 0:
                transport = SimTransport(SimDevice(param_file=SIM_PARAM_FILE))
            else:
                transport = SerialTransport(self.port_edit.currentText())
            link = DeviceLink(transport)
            status, _ = link.request(vp.Cmd.HELLO)
            if status != vp.Status.OK:
                raise LinkTimeout(f"HELLO: {status.name}")
            mask = self.channel_panel.mask() or DEFAULT_MASK
            link.request(vp.Cmd.TELEMETRY_START,
                         struct.pack("<IH", mask, DEFAULT_DECIMATION))
        except (LinkTimeout, OSError) as e:
            QMessageBox.critical(self, "Connect failed", str(e))
            return
        self.link = link
        self.connect_btn.setText("Disconnect")
        self._last_tick = time.monotonic()
        self._refresh_params()
        self.poll_timer.start()
        self.hb_timer.start()

    def _disconnect(self):
        self.poll_timer.stop()
        self.hb_timer.stop()
        if self.link is not None:
            try:
                self.link.request(vp.Cmd.TELEMETRY_STOP)
            except LinkTimeout:
                pass
            self.link.close()
        self.link = None
        self.connect_btn.setText("Connect")
        self.state_label.setText("DISCONNECTED")
        self.state_label.setStyleSheet("font-size:18px;font-weight:bold")

    def _simple_cmd(self, cmd):
        if self.link is None:
            return
        try:
            status, _ = self.link.request(cmd)
            if status != vp.Status.OK:
                self.statusBar().showMessage(f"{vp.Cmd(cmd).name}: {status.name}", 4000)
        except LinkTimeout as e:
            self.statusBar().showMessage(str(e), 4000)

    def _on_stop(self):
        self._simple_cmd(vp.Cmd.STOP)

    def _on_setpoint(self):
        if self.link is None:
            return
        mode = (vp.SetpointMode.TORQUE if self.mode_combo.currentIndex() == 0
                else vp.SetpointMode.SPEED)
        sign = 1.0 if self.dir_combo.currentIndex() == 0 else -1.0
        try:
            status = self.link.setpoint(mode, sign * self.sp_spin.value())
            if status != vp.Status.OK:
                self.statusBar().showMessage(f"SETPOINT: {status.name}", 4000)
        except LinkTimeout as e:
            self.statusBar().showMessage(str(e), 4000)

    def _handle_drive_key(self, key) -> bool:
        """Arrow-key drive; returns True when the key was consumed."""
        if not self.kb_drive_btn.isChecked() or self.link is None:
            return False
        step = (TORQUE_STEP_A if self.mode_combo.currentIndex() == 0
                else SPEED_STEP_RPM)
        if key == Qt.Key_Up:
            self.sp_spin.setValue(self.sp_spin.value() + step)
        elif key == Qt.Key_Down:
            self.sp_spin.setValue(max(0.0, self.sp_spin.value() - step))
        elif key in (Qt.Key_Left, Qt.Key_Right):
            self.dir_combo.setCurrentIndex(1 - self.dir_combo.currentIndex())
        else:
            return False
        self._on_setpoint()
        return True

    def keyPressEvent(self, event):
        if self._handle_drive_key(event.key()):
            return
        super().keyPressEvent(event)

    # ------------------------------------------------------------- params

    def _refresh_params(self):
        self.params_panel.refresh()

    # -------------------------------------------------------------- timers

    def _on_poll(self):
        if self.link is None:
            return
        now = time.monotonic()
        if isinstance(self.link.transport, SimTransport):
            self.link.transport.tick(now - self._last_tick)
        self._last_tick = now
        for f in self.link.poll():
            if f.cmd == vp.Cmd.TELEMETRY_DATA:
                batch = vp.parse_telemetry(f.payload)
                self.store.add_batch(batch)
                if self.csv_logger is not None:
                    self.csv_logger.add_batch(batch)
            elif f.cmd == vp.Cmd.MOTOR_ID_PROGRESS:
                self._on_motor_id(f.payload)
        self.plots.update_from(self.store)
        self.tiles.update_from(self.store)

    def _on_motor_id(self, payload):
        if self.motorid_wizard is not None:
            self.motorid_wizard.handle_progress(payload)
        stage, pct, r, ld, lq, flux = struct.unpack("<BBffff", payload)
        stage = vp.MotorIdStage(stage)
        self.statusBar().showMessage(f"Motor ID: {stage.name} {pct}%", 2000)
        if stage == vp.MotorIdStage.DONE:
            self.statusBar().showMessage(
                f"Motor ID done: R={r:.4g} Ld={ld:.4g} Lq={lq:.4g} flux={flux:.4g}", 8000)
            self._refresh_params()

    def _on_heartbeat(self):
        if self.link is None:
            return
        try:
            state, faults = self.link.heartbeat()
        except LinkTimeout:
            self.state_label.setText("LINK LOST")
            return
        self.state_label.setText(state.name)
        self.state_label.setStyleSheet(
            f"font-size:18px;font-weight:bold;color:{STATE_COLORS.get(state, '#808080')}")
        self.fault_label.setText(", ".join(vp.decode_faults(faults)))
        self.console.record_status(state, faults)


def run():
    app = QApplication([])
    theme.apply_dark(app)
    win = MainWindow()
    win.show()
    app.exec()
