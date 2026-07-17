"""Phase 1 UI foundation: dark theme, tabbed layout, port enumeration.

User journeys:
- As a tuner, I want a deliberate dark UI with a clear layout (Dashboard /
  Tuning / Parameters / Console tabs), so the tool feels purposeful and
  safety controls are always visible in the toolbar.
- As a user, I want to pick my serial port from a list instead of typing a
  device path.
"""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

import vortex_protocol as vp                             # noqa: E402
from PySide6.QtWidgets import QApplication, QTabWidget   # noqa: E402

from vortex_app import main as app_main                  # noqa: E402
from vortex_app import theme                             # noqa: E402
from vortex_app.link import list_serial_ports            # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_dark_palette_applied(qapp):
    theme.apply_dark(qapp)
    window = qapp.palette().window().color()
    text = qapp.palette().windowText().color()
    assert window.lightness() < 100          # dark background
    assert text.lightness() > 150            # light text
    assert theme.ACCENT.startswith("#")


def test_plot_colors_cover_every_channel():
    for ch in vp.CHANNELS:
        assert ch.name in theme.PLOT_COLORS


def test_window_has_tabbed_layout(qapp):
    win = app_main.MainWindow()
    tabs = win.findChild(QTabWidget, "main_tabs")
    assert tabs is not None
    # spec change (user, 2026-07-17): params live in a permanent side pane,
    # so the tab bar no longer has a Parameters tab
    labels = [tabs.tabText(i) for i in range(tabs.count())]
    assert labels == ["Dashboard", "Tuning", "Console"]


def test_safety_controls_and_pinned_attrs(qapp):
    win = app_main.MainWindow()
    # STOP stays in the always-visible toolbar, styled as the emergency action
    assert win.stop_btn.text().startswith("STOP")
    # attributes the smoke test (and later phases) rely on survive the split
    assert hasattr(win, "param_tree")
    assert hasattr(win, "state_label")
    assert hasattr(win, "store")


def test_list_serial_ports_returns_list():
    ports = list_serial_ports()
    assert isinstance(ports, list)
    assert all(isinstance(p, str) for p in ports)
