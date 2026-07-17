"""Channel selector panel + unit-grouped live plots.

Channel visibility is a device-side concern: checking boxes changes the
telemetry mask the device streams (mask_changed -> TELEMETRY_START restart),
not just curve visibility. Plots get one row per physical unit present.
"""

from __future__ import annotations

import pyqtgraph as pg
import vortex_protocol as vp
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QTreeWidget, QTreeWidgetItem, QVBoxLayout,
                               QWidget)

from vortex_app import theme

# (unit key, group label, plot row title) in display order
UNIT_GROUPS = [
    ("A", "Currents", "Current [A]"),
    ("V", "Voltages", "Voltage [V]"),
    ("rpm", "Motion", "Speed [rpm]"),
    ("rad", "Angle", "Angle [rad]"),
    ("degC", "Temperatures", "Temperature [°C]"),
]
_UNIT_LABEL = {u: (g, t) for u, g, t in UNIT_GROUPS}


class ChannelPanel(QWidget):
    """Checkbox tree of telemetry channels; check state == stream mask."""

    mask_changed = Signal(int)

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Channels"])
        layout.addWidget(self.tree)
        self._items: dict[str, QTreeWidgetItem] = {}

        groups: dict[str, QTreeWidgetItem] = {}
        for ch in vp.CHANNELS:
            label = _UNIT_LABEL.get(ch.unit, ("Other", ""))[0]
            group = groups.get(label)
            if group is None:
                group = groups[label] = QTreeWidgetItem(self.tree, [label])
                group.setExpanded(True)
            item = QTreeWidgetItem(group, [ch.name])
            item.setForeground(0, pg.mkBrush(theme.PLOT_COLORS[ch.name]))
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(0, Qt.Unchecked)
            item.setData(0, Qt.UserRole, ch.bit)
            self._items[ch.name] = item
        self.tree.itemChanged.connect(self._on_item_changed)

    def _on_item_changed(self, item, _col):
        if item.data(0, Qt.UserRole) is not None:
            self.mask_changed.emit(self.mask())

    def mask(self) -> int:
        return sum(1 << item.data(0, Qt.UserRole)
                   for item in self._items.values()
                   if item.checkState(0) == Qt.Checked)

    def set_mask(self, mask: int) -> None:
        self.tree.blockSignals(True)
        for name, item in self._items.items():
            bit = item.data(0, Qt.UserRole)
            item.setCheckState(0, Qt.Checked if mask & (1 << bit)
                               else Qt.Unchecked)
        self.tree.blockSignals(False)

    def set_channel_checked(self, name: str, checked: bool) -> None:
        self._items[name].setCheckState(0, Qt.Checked if checked
                                        else Qt.Unchecked)


class LivePlots(QWidget):
    """One time-linked plot row per unit; curves follow the stream mask."""

    def __init__(self, n_points: int = 2000):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.glw = pg.GraphicsLayoutWidget()
        layout.addWidget(self.glw)
        self.curves: dict[str, pg.PlotDataItem] = {}
        self.plot_count = 0
        self.paused = False
        self.n_points = n_points

    def rebuild(self, mask: int) -> None:
        self.glw.clear()
        self.curves.clear()
        self.plot_count = 0
        chans = vp.active_channels(mask)
        first = None
        for unit, _group, title in UNIT_GROUPS:
            members = [c for c in chans if c.unit == unit]
            if not members:
                continue
            plot = self.glw.addPlot(title=title)
            plot.showGrid(x=True, y=True, alpha=0.15)
            plot.addLegend(offset=(4, 4))
            if first is None:
                first = plot
            else:
                plot.setXLink(first)
            for ch in members:
                self.curves[ch.name] = plot.plot(
                    pen=theme.PLOT_COLORS[ch.name], name=ch.name)
            self.glw.nextRow()
            self.plot_count += 1

    def update_from(self, store) -> None:
        if self.paused:
            return
        for name, curve in self.curves.items():
            t, v = store.window(name, self.n_points)
            if t.size:
                curve.setData(t, v)

    def clear(self) -> None:
        for curve in self.curves.values():
            curve.setData([], [])
