"""Vortex control app main window.

Thin GUI over DeviceLink + TelemetryStore. Runs against the in-process
simulator or a serial port (real hardware / `python -m simulator` pty).
"""

from __future__ import annotations

import struct
import time
from pathlib import Path

import pyqtgraph as pg
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (QApplication, QComboBox, QDoubleSpinBox,
                               QHBoxLayout, QLabel, QMainWindow, QMessageBox,
                               QPushButton, QTabWidget, QVBoxLayout, QWidget)

import vortex_protocol as vp
from simulator import SimDevice
from vortex_app import theme
from vortex_app.link import (DeviceLink, LinkTimeout, SerialTransport,
                             SimTransport, list_serial_ports)
from vortex_app.rings import TelemetryStore
from vortex_app.widgets.params import ParamPanel

POLL_MS = 30
PLOT_POINTS = 2000
DEFAULT_MASK = 0x1C7 | (1 << 12)  # ia ib ic vbus id iq + speed
DEFAULT_DECIMATION = 8
SIM_PARAM_FILE = Path.home() / ".vortex_sim_params.json"

CURRENT_CHANNELS = ("ia", "ib", "ic")
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
        self.tabs = QTabWidget(objectName="main_tabs")
        self.tabs.addTab(self._build_dashboard_tab(), "Dashboard")
        self.tabs.addTab(QWidget(), "Tuning")        # populated in Phase 4
        self.tabs.addTab(self._build_params_tab(), "Parameters")
        self.tabs.addTab(QWidget(), "Console")       # populated in Phase 5
        layout.addWidget(self.tabs, 1)
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
        self.sp_spin = QDoubleSpinBox(minimum=-30000, maximum=30000, decimals=2)
        self.apply_btn = QPushButton("Set")
        self.apply_btn.clicked.connect(self._on_setpoint)
        self.motorid_btn = QPushButton("Identify motor")
        self.motorid_btn.clicked.connect(lambda: self._simple_cmd(vp.Cmd.MOTOR_ID_START))
        for w in (self.port_combo, self.port_edit, self.connect_btn, self.arm_btn,
                  self.disarm_btn, self.stop_btn, self.mode_combo, self.sp_spin,
                  self.apply_btn, self.motorid_btn):
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
        return self._build_plots()

    def _build_params_tab(self):
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

    def _build_plots(self):
        glw = pg.GraphicsLayoutWidget()
        self.curves = {}
        p1 = glw.addPlot(title="Phase currents [A]")
        p1.addLegend()
        for name in CURRENT_CHANNELS:
            self.curves[name] = p1.plot(pen=theme.PLOT_COLORS[name], name=name)
        glw.nextRow()
        p2 = glw.addPlot(title="Bus voltage [V]")
        self.curves["vbus"] = p2.plot(pen=theme.PLOT_COLORS["vbus"])
        glw.nextRow()
        p3 = glw.addPlot(title="Speed [rpm]")
        self.curves["speed"] = p3.plot(pen=theme.PLOT_COLORS["speed"])
        for p in (p2, p3):
            p.setXLink(p1)
        return glw

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
            link.request(vp.Cmd.TELEMETRY_START,
                         struct.pack("<IH", DEFAULT_MASK, DEFAULT_DECIMATION))
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
        try:
            status = self.link.setpoint(mode, self.sp_spin.value())
            if status != vp.Status.OK:
                self.statusBar().showMessage(f"SETPOINT: {status.name}", 4000)
        except LinkTimeout as e:
            self.statusBar().showMessage(str(e), 4000)

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
                self.store.add_batch(vp.parse_telemetry(f.payload))
            elif f.cmd == vp.Cmd.MOTOR_ID_PROGRESS:
                self._on_motor_id(f.payload)
        for name, curve in self.curves.items():
            t, v = self.store.window(name, PLOT_POINTS)
            if t.size:
                curve.setData(t, v)

    def _on_motor_id(self, payload):
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


def run():
    app = QApplication([])
    theme.apply_dark(app)
    win = MainWindow()
    win.show()
    app.exec()
