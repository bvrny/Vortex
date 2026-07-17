"""Deliberate dark theme: Qt palette + pyqtgraph defaults + channel colors."""

from __future__ import annotations

import pyqtgraph as pg
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

ACCENT = "#4fc3f7"
BG = "#16181d"          # window background
BG_ALT = "#1e2128"      # panels / inputs
FG = "#dfe3ea"          # primary text
FG_DIM = "#8b93a1"
DANGER = "#e05252"
WARN = "#d8a03c"
OK = "#4caf78"

# One deterministic pen color per telemetry channel (phase triplets share
# hue families: currents saturated, voltages softer, dq/temps distinct).
PLOT_COLORS = {
    "ia": "#ff5252", "ib": "#69f0ae", "ic": "#448aff",
    "va": "#ff8a80", "vb": "#b9f6ca", "vc": "#82b1ff",
    "vbus": "#ffd54f",
    "id": "#ba68c8", "iq": "#4dd0e1",
    "vd": "#f06292", "vq": "#4db6ac",
    "angle_elec": "#90a4ae",
    "speed": "#b388ff",
    "iq_setpoint": "#eceff1",
    "temp_inv1": "#ef9a9a", "temp_inv2": "#ffcc80", "temp_inv3": "#fff59d",
    "temp_motor": "#ff7043",
}


def apply_dark(app: QApplication) -> None:
    """Fusion style + dark palette + matching pyqtgraph config. Idempotent."""
    app.setStyle("Fusion")
    pal = QPalette()
    pal.setColor(QPalette.Window, QColor(BG))
    pal.setColor(QPalette.WindowText, QColor(FG))
    pal.setColor(QPalette.Base, QColor(BG_ALT))
    pal.setColor(QPalette.AlternateBase, QColor(BG))
    pal.setColor(QPalette.Text, QColor(FG))
    pal.setColor(QPalette.Button, QColor(BG_ALT))
    pal.setColor(QPalette.ButtonText, QColor(FG))
    pal.setColor(QPalette.ToolTipBase, QColor(BG_ALT))
    pal.setColor(QPalette.ToolTipText, QColor(FG))
    pal.setColor(QPalette.Highlight, QColor(ACCENT))
    pal.setColor(QPalette.HighlightedText, QColor("#10131a"))
    pal.setColor(QPalette.PlaceholderText, QColor(FG_DIM))
    pal.setColor(QPalette.Disabled, QPalette.Text, QColor(FG_DIM))
    pal.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(FG_DIM))
    pal.setColor(QPalette.Disabled, QPalette.WindowText, QColor(FG_DIM))
    app.setPalette(pal)

    pg.setConfigOptions(antialias=True, background=BG, foreground=FG_DIM)
