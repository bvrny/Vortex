"""Current-loop tuning aids: bandwidth knob, step capture, motor-ID flow.

The bandwidth knob is the single tuning input: kp = L*w_bw, ki = R*w_bw from
the identified motor parameters (same math as the firmware's vx_motor_id and
the spec's default gains). Capture-by-scope gives the evidence.
"""

from __future__ import annotations

import math
import struct

import vortex_protocol as vp
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QDoubleSpinBox, QFormLayout,
                               QHBoxLayout, QLabel, QProgressBar, QPushButton,
                               QVBoxLayout, QWidget)

from vortex_app import theme


def compute_iloop_gains(r_ohm: float, l_h: float,
                        bandwidth_hz: float) -> tuple[float, float]:
    w_bw = 2.0 * math.pi * bandwidth_hz
    return l_h * w_bw, r_ohm * w_bw


def run_step_capture(link, mode: vp.SetpointMode, amplitude: float,
                     mask: int, decimation: int,
                     pretrigger: int = 0) -> vp.TelemetryBatch:
    """Arm the scope, apply a setpoint step, read back the capture."""
    for status in (link.scope_config(mask, decimation, pretrigger),
                   link.scope_arm(),
                   link.setpoint(mode, amplitude)):
        if status != vp.Status.OK:
            raise RuntimeError(f"step capture: {status.name}")
    status, blob = link.scope_read()
    if status != vp.Status.OK:
        raise RuntimeError(f"SCOPE_READ: {status.name}")
    return vp.parse_telemetry(blob)


class BandwidthKnob(QWidget):
    """One knob: current-loop bandwidth -> kp/ki written to the device."""

    def __init__(self, link_getter):
        super().__init__()
        self.link = link_getter
        meta = vp.PARAM_BY_NAME["iloop.bandwidth_hz"]
        form = QFormLayout(self)
        form.setContentsMargins(0, 0, 0, 0)
        self.bw_spin = QDoubleSpinBox(minimum=meta.min, maximum=meta.max,
                                      decimals=0, suffix=" Hz")
        self.bw_spin.setValue(meta.default)
        self.gains_label = QLabel("")
        self.apply_btn = QPushButton("Compute && write gains")
        self.apply_btn.clicked.connect(self.apply)
        form.addRow("Current-loop bandwidth", self.bw_spin)
        form.addRow("Resulting gains", self.gains_label)
        form.addRow(self.apply_btn)

    def set_bandwidth(self, hz: float) -> None:
        self.bw_spin.setValue(hz)

    def apply(self) -> vp.Status:
        link = self.link()
        if link is None:
            return vp.Status.NACK_BAD_STATE
        r = link.read_param("motor.r_phase")
        l_d = link.read_param("motor.l_d")
        bw = self.bw_spin.value()
        kp, ki = compute_iloop_gains(r, l_d, bw)
        for name, value in (("iloop.kp", kp), ("iloop.ki", ki),
                            ("iloop.bandwidth_hz", bw)):
            status = link.write_param(name, value)
            if status != vp.Status.OK:
                return status
        self.gains_label.setText(
            f"kp = {kp:.4g} V/A   ki = {ki:.4g} V/(A·s)   (R={r:.4g}, L={l_d:.4g})")
        return vp.Status.OK


class MotorIdMonitor:
    """Tracks MOTOR_ID_PROGRESS frames into stage/percent/results."""

    def __init__(self):
        self.stage = vp.MotorIdStage.IDLE
        self.percent = 0
        self.done = False
        self.failed = False
        self.results: dict[str, float] = {}

    def handle_progress(self, payload: bytes) -> None:
        stage, pct, r, l_d, l_q, flux = struct.unpack("<BBffff", payload)
        self.stage = vp.MotorIdStage(stage)
        self.percent = pct
        if self.stage == vp.MotorIdStage.DONE:
            self.done = True
            self.results = {"r_phase": r, "l_d": l_d, "l_q": l_q, "flux": flux}
        elif self.stage == vp.MotorIdStage.FAILED:
            self.done = True
            self.failed = True


class MotorIdWizard(QDialog):
    """Guided motor identification: safety note -> progress -> results."""

    def __init__(self, parent, start_cmd):
        super().__init__(parent)
        self.setWindowTitle("Motor identification")
        self.monitor = MotorIdMonitor()
        layout = QVBoxLayout(self)
        note = QLabel("The motor will be energized and may move.\n"
                      "Ensure the shaft is free to rotate and clear of tools.")
        note.setStyleSheet(f"color:{theme.WARN}")
        layout.addWidget(note)
        self.progress = QProgressBar(minimum=0, maximum=100)
        self.stage_label = QLabel("idle")
        self.result_label = QLabel("")
        self.result_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.progress)
        layout.addWidget(self.stage_label)
        layout.addWidget(self.result_label)
        row = QHBoxLayout()
        self.start_btn = QPushButton("Start")
        self.start_btn.clicked.connect(lambda: (start_cmd(),
                                                self.start_btn.setEnabled(False)))
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        row.addWidget(self.start_btn)
        row.addWidget(close_btn)
        layout.addLayout(row)

    def handle_progress(self, payload: bytes) -> None:
        self.monitor.handle_progress(payload)
        self.progress.setValue(self.monitor.percent)
        self.stage_label.setText(self.monitor.stage.name)
        if self.monitor.failed:
            self.result_label.setText("Identification FAILED")
            self.result_label.setStyleSheet(f"color:{theme.DANGER}")
            self.start_btn.setEnabled(True)
        elif self.monitor.done:
            r = self.monitor.results
            self.result_label.setText(
                f"R = {r['r_phase']:.4g} Ω\nLd = {r['l_d']:.4g} H\n"
                f"Lq = {r['l_q']:.4g} H\nflux = {r['flux']:.4g} Wb\n"
                "Values applied to the motor parameters (save to flash to keep).")
