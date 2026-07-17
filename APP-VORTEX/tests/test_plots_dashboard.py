"""Phase 3: channel selector panel, unit-grouped live plots, tiles, CSV log.

User journeys:
- As a tuner, I want to pick plotted channels from a checkbox panel (not
  in-plot legend toggles), and have the device stream only those channels.
- As a tuner, I want plots grouped by unit with pause/clear, and key values
  as big dashboard tiles.
- As a user, I want to record the live stream to CSV for offline analysis.
"""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

import vortex_protocol as vp                                  # noqa: E402
from PySide6.QtWidgets import QApplication                    # noqa: E402

from vortex_app.csvlog import CsvLogger                       # noqa: E402
from vortex_app.rings import TelemetryStore                   # noqa: E402
from vortex_app.widgets.dashboard import StatTiles            # noqa: E402
from vortex_app.widgets.plots import ChannelPanel, LivePlots  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _bit(name):
    return 1 << vp.CHANNEL_BY_NAME[name].bit


def _batch(mask, samples):
    """Build+parse a telemetry batch (samples = [(t_off_us, (raw,...)), ...],
    raw values in ascending mask-bit order)."""
    return vp.parse_telemetry(vp.build_telemetry(0, mask, 8, samples))


def test_channel_panel_mask_roundtrip(qapp):
    panel = ChannelPanel()
    mask = _bit("ia") | _bit("ib") | _bit("speed")
    panel.set_mask(mask)
    assert panel.mask() == mask

    received = []
    panel.mask_changed.connect(received.append)
    panel.set_channel_checked("vbus", True)
    assert received[-1] == mask | _bit("vbus")
    panel.set_channel_checked("ia", False)
    assert received[-1] == (mask | _bit("vbus")) & ~_bit("ia")


def test_live_plots_one_row_per_unit(qapp):
    plots = LivePlots()
    plots.rebuild(_bit("ia") | _bit("ib") | _bit("vbus") | _bit("speed"))
    assert set(plots.curves) == {"ia", "ib", "vbus", "speed"}
    assert plots.plot_count == 3          # A row, V row, rpm row


def test_live_plots_pause_freezes_curves(qapp):
    store = TelemetryStore()
    plots = LivePlots()
    plots.rebuild(_bit("ia"))
    store.add_batch(_batch(_bit("ia"), [(0, (100,)), (200, (200,))]))
    plots.update_from(store)
    x1, _ = plots.curves["ia"].getData()
    n_before = len(x1)

    store.add_batch(_batch(_bit("ia"), [(400, (300,))]))
    plots.paused = True
    plots.update_from(store)
    x2, _ = plots.curves["ia"].getData()
    assert len(x2) == n_before            # frozen while paused

    plots.paused = False
    plots.update_from(store)
    x3, _ = plots.curves["ia"].getData()
    assert len(x3) == n_before + 1


def test_csv_logger_writes_scaled_rows(tmp_path):
    path = tmp_path / "log.csv"
    mask = _bit("ia") | _bit("vbus")
    log = CsvLogger(path, mask)
    log.add_batch(_batch(mask, [(0, (100, 19200)), (200, (200, 19200))]))
    log.close()

    lines = path.read_text().strip().splitlines()
    assert lines[0] == "t,ia,vbus"
    assert len(lines) == 3
    _t0, ia0, vbus0 = lines[1].split(",")
    assert float(ia0) == pytest.approx(1.0)      # 100 * 0.01 A/LSB
    assert float(vbus0) == pytest.approx(48.0)   # 19200 * 0.0025 V/LSB
    assert log.rows_written == 2


def test_stat_tiles_show_latest_values(qapp):
    store = TelemetryStore()
    mask = _bit("vbus") | _bit("iq") | _bit("speed")
    # ascending bit order: vbus(6), iq(8), speed(12)
    store.add_batch(_batch(mask, [(0, (19200, 1500, 1000))]))
    tiles = StatTiles()
    tiles.update_from(store)
    assert "48" in tiles.text("vbus")
    assert tiles.text("speed") != "—"
    # a store with no data leaves the placeholder
    empty = StatTiles()
    empty.update_from(TelemetryStore())
    assert empty.text("vbus") == "—"
