"""Scope panel: triggered high-rate capture with step-response workflow."""

from __future__ import annotations

import pyqtgraph as pg
import vortex_protocol as vp
from PySide6.QtWidgets import (QComboBox, QDoubleSpinBox, QFileDialog,
                               QFormLayout, QHBoxLayout, QPushButton,
                               QSpinBox, QVBoxLayout, QWidget)

from vortex_app import theme
from vortex_app.csvlog import CsvLogger
from vortex_app.widgets.plots import ChannelPanel
from vortex_app.widgets.tuning import run_step_capture

DEFAULT_SCOPE_MASK = 0x7 | (1 << 8)   # ia ib ic + iq
DEFAULT_DECIMATION = 1                # full rate: that's what a scope is for


class ScopePanel(QWidget):
    def __init__(self, link_getter):
        super().__init__()
        self.link = link_getter
        self.last_batch: vp.TelemetryBatch | None = None

        layout = QHBoxLayout(self)
        left = QVBoxLayout()
        self.channels = ChannelPanel()
        self.channels.set_mask(DEFAULT_SCOPE_MASK)
        left.addWidget(self.channels, 1)

        form = QFormLayout()
        self.dec_spin = QSpinBox(minimum=1, maximum=40000,
                                 value=DEFAULT_DECIMATION)
        self.pretrig_spin = QSpinBox(minimum=0, maximum=65535, value=0)
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["Torque (A)", "Speed (rpm)"])
        self.amp_spin = QDoubleSpinBox(minimum=-30000, maximum=30000,
                                       decimals=2, value=1.0)
        form.addRow("Decimation", self.dec_spin)
        form.addRow("Pre-trigger", self.pretrig_spin)
        form.addRow("Step mode", self.mode_combo)
        form.addRow("Step amplitude", self.amp_spin)
        left.addLayout(form)

        row = QHBoxLayout()
        self.capture_btn = QPushButton("Capture")
        self.capture_btn.clicked.connect(lambda: self.capture(step=False))
        self.step_btn = QPushButton("Step capture")
        self.step_btn.clicked.connect(lambda: self.capture(step=True))
        self.export_btn = QPushButton("Export CSV")
        self.export_btn.clicked.connect(self._on_export)
        row.addWidget(self.capture_btn)
        row.addWidget(self.step_btn)
        row.addWidget(self.export_btn)
        left.addLayout(row)

        self.glw = pg.GraphicsLayoutWidget()
        self.plot = self.glw.addPlot(title="Scope capture")
        self.plot.showGrid(x=True, y=True, alpha=0.2)
        self.plot.addLegend(offset=(4, 4))
        layout.addLayout(left, 0)
        layout.addWidget(self.glw, 1)

    # ------------------------------------------------------------- actions

    def capture(self, step: bool) -> bool:
        link = self.link()
        if link is None:
            return False
        mask = self.channels.mask() or DEFAULT_SCOPE_MASK
        try:
            if step:
                mode = (vp.SetpointMode.TORQUE
                        if self.mode_combo.currentIndex() == 0
                        else vp.SetpointMode.SPEED)
                batch = run_step_capture(link, mode, self.amp_spin.value(),
                                         mask, self.dec_spin.value(),
                                         self.pretrig_spin.value())
            else:
                for status in (link.scope_config(mask, self.dec_spin.value(),
                                                 self.pretrig_spin.value()),
                               link.scope_arm()):
                    if status != vp.Status.OK:
                        raise RuntimeError(status.name)
                status, blob = link.scope_read()
                if status != vp.Status.OK:
                    raise RuntimeError(status.name)
                batch = vp.parse_telemetry(blob)
        except Exception as e:                  # incl. LinkTimeout
            self.plot.setTitle(f"Scope capture — failed: {e}")
            return False
        self.last_batch = batch
        self._draw(batch)
        return True

    def _draw(self, batch: vp.TelemetryBatch) -> None:
        self.plot.clear()
        self.plot.setTitle("Scope capture")
        chans = vp.active_channels(batch.channel_mask)
        t = [off / 1e6 for off, _ in batch.samples]
        for j, ch in enumerate(chans):
            v = [vals[j] * ch.scale for _, vals in batch.samples]
            self.plot.plot(t, v, pen=theme.PLOT_COLORS[ch.name], name=ch.name)

    def _on_export(self) -> None:
        if self.last_batch is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export scope capture", "scope.csv", "CSV (*.csv)")
        if not path:
            return
        log = CsvLogger(path, self.last_batch.channel_mask)
        log.add_batch(self.last_batch)
        log.close()
