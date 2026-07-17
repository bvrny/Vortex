"""Numpy ring buffers that hold telemetry history for plotting."""

import numpy as np

import vortex_protocol as vp
from vortex_app.rings import ChannelRing, TelemetryStore


def test_ring_wraps_and_keeps_latest():
    r = ChannelRing(capacity=8)
    r.append(np.arange(10.0), np.arange(10.0) * 2.0)
    t, v = r.window()
    assert len(t) == 8
    assert t[0] == 2.0 and t[-1] == 9.0        # oldest two dropped
    assert v[-1] == 18.0
    assert np.all(np.diff(t) > 0)              # chronological


def test_ring_window_subset():
    r = ChannelRing(capacity=100)
    r.append(np.arange(5.0), np.ones(5))
    t, v = r.window(3)
    assert list(t) == [2.0, 3.0, 4.0]


def test_store_scales_and_routes_channels():
    mask = (1 << vp.CHANNEL_BY_NAME["ia"].bit) | (1 << vp.CHANNEL_BY_NAME["vbus"].bit)
    # two samples, 100 us apart: (ia_raw, vbus_raw) in ascending bit order
    payload = vp.build_telemetry(1_000_000, mask, 8, [(0, (100, 19200)),
                                                      (100, (200, 19200))])
    store = TelemetryStore(capacity=64)
    store.add_batch(vp.parse_telemetry(payload))
    t, ia = store.window("ia")
    _, vbus = store.window("vbus")
    assert ia == [1.0, 2.0] if isinstance(ia, list) else np.allclose(ia, [1.0, 2.0])
    assert np.allclose(vbus, [48.0, 48.0])
    assert np.allclose(t, [1.0, 1.0001])       # seconds
    assert store.window("iq")[0].size == 0     # inactive channel stays empty
