"""Polar d/q plane: live current and voltage vectors.

Both vectors are auto-normalized to their own running peak so they stay
readable on one unit circle; the labels carry the real magnitudes/angles.
"""

from __future__ import annotations

import math

import numpy as np
import pyqtgraph as pg
from PySide6.QtWidgets import QVBoxLayout, QWidget

from vortex_app import theme

I_COLOR = theme.PLOT_COLORS["iq"]
V_COLOR = theme.PLOT_COLORS["vq"]


class PolarDQ(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        plot = pg.PlotWidget()
        plot.setAspectLocked(True)
        plot.hideAxis("bottom")
        plot.hideAxis("left")
        plot.setMouseEnabled(False, False)
        plot.setRange(xRange=(-1.35, 1.35), yRange=(-1.35, 1.35))
        layout.addWidget(plot)
        self.plot = plot

        grid_pen = pg.mkPen(theme.FG_DIM, width=1, style=pg.QtCore.Qt.DotLine)
        theta = np.linspace(0.0, 2.0 * math.pi, 90)
        for r in (1.0 / 3.0, 2.0 / 3.0, 1.0):
            plot.plot(r * np.cos(theta), r * np.sin(theta), pen=grid_pen)
        for deg in range(0, 180, 30):
            a = math.radians(deg)
            plot.plot([-math.cos(a), math.cos(a)],
                      [-math.sin(a), math.sin(a)], pen=grid_pen)
        for text, x, y in (("d", 1.12, 0.0), ("q", 0.0, 1.12)):
            axis = pg.TextItem(text, color=theme.FG_DIM, anchor=(0.5, 0.5))
            axis.setPos(x, y)
            plot.addItem(axis)

        self.i_arrow = plot.plot([], [], pen=pg.mkPen(I_COLOR, width=3))
        self.v_arrow = plot.plot([], [], pen=pg.mkPen(V_COLOR, width=3))
        self._i_text = pg.TextItem(color=I_COLOR, anchor=(0, 0))
        self._i_text.setPos(-1.3, 1.3)
        self._v_text = pg.TextItem(color=V_COLOR, anchor=(0, 1))
        self._v_text.setPos(-1.3, -1.3)
        plot.addItem(self._i_text)
        plot.addItem(self._v_text)
        # QGraphicsTextItem handles (toPlainText) for tests/tooling
        self.i_label = self._i_text.textItem
        self.v_label = self._v_text.textItem

        self._i_peak = 1e-6
        self._v_peak = 1e-6

    def _draw(self, arrow, text_item, d, q, peak, unit):
        mag = math.hypot(d, q)
        peak = max(peak, mag)
        r = mag / peak if peak > 0.0 else 0.0
        angle = math.atan2(q, d)
        arrow.setData([0.0, r * math.cos(angle)], [0.0, r * math.sin(angle)])
        text_item.setText(f"|{unit[0]}| = {mag:.1f} {unit[1]}  "
                          f"∠ {math.degrees(angle):.0f}°")
        return peak

    def update_vectors(self, i_d: float, i_q: float,
                       v_d: float, v_q: float) -> None:
        self._i_peak = self._draw(self.i_arrow, self._i_text, i_d, i_q,
                                  self._i_peak, ("I", "A"))
        self._v_peak = self._draw(self.v_arrow, self._v_text, v_d, v_q,
                                  self._v_peak, ("V", "V"))

    def update_from(self, store) -> None:
        values = {}
        for name in ("id", "iq", "vd", "vq"):
            t, v = store.window(name, 1)
            if not t.size:
                return                      # channels not streaming yet
            values[name] = float(v[-1])
        self.update_vectors(values["id"], values["iq"],
                            values["vd"], values["vq"])
