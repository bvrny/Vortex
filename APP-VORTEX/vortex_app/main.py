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
                               QHBoxLayout, QInputDialog, QLabel, QLineEdit,
                               QMainWindow, QMessageBox, QPushButton,
                               QTreeWidget, QTreeWidgetItem, QVBoxLayout,
                               QWidget)

import vortex_protocol as vp
from simulator import SimDevice
from vortex_app.link import DeviceLink, LinkTimeout, SerialTransport, SimTransport
from vortex_app.rings import TelemetryStore

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
        root = QWidget()
        layout = QHBoxLayout(root)
        layout.addLayout(self._build_left_panel(), 0)
        layout.addWidget(self._build_plots(), 1)
        self.setCentralWidget(root)
        self._build_toolbar()

    def _build_toolbar(self):
        tb = self.addToolBar("main")
        tb.setMovable(False)
        self.port_combo = QComboBox()
        self.port_combo.addItems(["In-process simulator", "Serial port:"])
        self.port_edit = QLineEdit("/dev/ttyACM0")
        self.port_edit.setMaximumWidth(160)
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

    def _build_left_panel(self):
        panel = QVBoxLayout()
        self.state_label = QLabel("DISCONNECTED")
        self.state_label.setStyleSheet("font-size:18px;font-weight:bold")
        self.fault_label = QLabel("")
        self.fault_label.setStyleSheet("color:#c80000")
        self.fault_label.setWordWrap(True)
        clear_btn = QPushButton("Clear faults")
        clear_btn.clicked.connect(lambda: self._simple_cmd(vp.Cmd.FAULT_CLEAR))
        panel.addWidget(self.state_label)
        panel.addWidget(self.fault_label)
        panel.addWidget(clear_btn)

        self.param_tree = QTreeWidget()
        self.param_tree.setHeaderLabels(["Parameter", "Value", "Unit"])
        self.param_tree.setColumnWidth(0, 200)
        self.param_tree.itemDoubleClicked.connect(self._on_param_edit)
        panel.addWidget(self.param_tree, 1)

        row = QHBoxLayout()
        for label, cmd in (("Save to flash", vp.Cmd.PARAM_SAVE),
                           ("Load", vp.Cmd.PARAM_LOAD),
                           ("Defaults", vp.Cmd.PARAM_DEFAULT)):
            b = QPushButton(label)
            b.clicked.connect(lambda _=False, c=cmd: (self._simple_cmd(c),
                                                      self._refresh_params()))
            row.addWidget(b)
        panel.addLayout(row)
        return panel

    def _build_plots(self):
        pg.setConfigOptions(antialias=False)
        glw = pg.GraphicsLayoutWidget()
        self.curves = {}
        p1 = glw.addPlot(title="Phase currents [A]")
        p1.addLegend()
        for name, color in zip(CURRENT_CHANNELS, ("#ff5050", "#50ff50", "#5090ff")):
            self.curves[name] = p1.plot(pen=color, name=name)
        glw.nextRow()
        p2 = glw.addPlot(title="Bus voltage [V]")
        self.curves["vbus"] = p2.plot(pen="#ffc850")
        glw.nextRow()
        p3 = glw.addPlot(title="Speed [rpm]")
        self.curves["speed"] = p3.plot(pen="#c890ff")
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
                transport = SerialTransport(self.port_edit.text())
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
        if self.link is None:
            return
        self.param_tree.clear()
        groups: dict[str, QTreeWidgetItem] = {}
        for meta in sorted(vp.PARAMS.values(), key=lambda m: m.id):
            g = groups.get(meta.group)
            if g is None:
                g = groups[meta.group] = QTreeWidgetItem(self.param_tree, [meta.group])
                g.setExpanded(True)
            try:
                value = self.link.read_param(meta.name)
            except LinkTimeout:
                value = "?"
            if meta.enum_values is not None and value != "?":
                shown = meta.enum_values[int(value)]
            else:
                shown = f"{value:.6g}" if isinstance(value, float) else str(value)
            item = QTreeWidgetItem(g, [meta.name.split(".", 1)[1], shown, meta.unit])
            item.setData(0, Qt.UserRole, meta.name)

    def _on_param_edit(self, item, _col):
        name = item.data(0, Qt.UserRole)
        if self.link is None or name is None:
            return
        meta = vp.PARAM_BY_NAME[name]
        try:
            current = self.link.read_param(name)
            if meta.enum_values is not None:
                choice, ok = QInputDialog.getItem(
                    self, name, "Value:", list(meta.enum_values), int(current), False)
                value = meta.enum_values.index(choice) if ok else None
            elif meta.type == vp.ParamType.F32:
                value, ok = QInputDialog.getDouble(
                    self, name, f"Value [{meta.unit}] ({meta.min:g}..{meta.max:g}):",
                    float(current), meta.min, meta.max, 6)
                value = value if ok else None
            else:
                value, ok = QInputDialog.getInt(
                    self, name, f"Value [{meta.unit}] ({meta.min:g}..{meta.max:g}):",
                    int(current), int(meta.min), int(meta.max))
                value = value if ok else None
            if value is None:
                return
            status = self.link.write_param(name, value)
            if status != vp.Status.OK:
                self.statusBar().showMessage(f"PARAM_WRITE {name}: {status.name}", 4000)
        except LinkTimeout as e:
            self.statusBar().showMessage(str(e), 4000)
        self._refresh_params()

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
    win = MainWindow()
    win.show()
    app.exec()
