"""Dashboard stat tiles: big live readouts of the key quantities."""

from __future__ import annotations

from PySide6.QtWidgets import QGridLayout, QLabel, QVBoxLayout, QWidget

from vortex_app import theme

PLACEHOLDER = "—"

# (channel name, tile label, format, unit suffix)
TILE_DEFS = [
    ("speed", "Speed", ".0f", "rpm"),
    ("iq", "Iq", ".2f", "A"),
    ("id", "Id", ".2f", "A"),
    ("vbus", "Bus voltage", ".1f", "V"),
    ("temp_inv1", "Inverter temp", ".1f", "°C"),
    ("temp_motor", "Motor temp", ".1f", "°C"),
]
_COLUMNS = 3


class StatTiles(QWidget):
    """Grid of labeled numeric tiles fed from the TelemetryStore."""

    def __init__(self):
        super().__init__()
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        self._values: dict[str, QLabel] = {}
        for i, (name, label, _fmt, _unit) in enumerate(TILE_DEFS):
            tile = QWidget()
            tile.setStyleSheet(
                f"background:{theme.BG_ALT};border-radius:6px")
            box = QVBoxLayout(tile)
            box.setContentsMargins(10, 6, 10, 6)
            caption = QLabel(label)
            caption.setStyleSheet(f"color:{theme.FG_DIM};font-size:11px")
            value = QLabel(PLACEHOLDER)
            value.setStyleSheet("font-size:22px;font-weight:bold")
            box.addWidget(caption)
            box.addWidget(value)
            grid.addWidget(tile, i // _COLUMNS, i % _COLUMNS)
            self._values[name] = value

    def text(self, name: str) -> str:
        return self._values[name].text()

    def update_from(self, store) -> None:
        for name, label, fmt, unit in TILE_DEFS:
            t, v = store.window(name, 1)
            if t.size:
                self._values[name].setText(f"{v[-1]:{fmt}} {unit}")
