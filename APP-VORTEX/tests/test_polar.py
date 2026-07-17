"""Polar d/q vector view.

User journey: as a tuner, I want the current (id, iq) and voltage (vd, vq)
vectors drawn on the d-q plane in polar form, live, so I can see the field
orientation at a glance.
"""

import math
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

import vortex_protocol as vp                                  # noqa: E402
from PySide6.QtWidgets import QApplication                    # noqa: E402

from vortex_app.rings import TelemetryStore                   # noqa: E402
from vortex_app.widgets.polar import PolarDQ                  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _bit(name):
    return 1 << vp.CHANNEL_BY_NAME[name].bit


def test_vectors_drawn_and_labeled(qapp):
    polar = PolarDQ()
    polar.update_vectors(i_d=3.0, i_q=4.0, v_d=1.0, v_q=0.0)
    xi, yi = polar.i_arrow.getData()
    assert (xi[0], yi[0]) == (0.0, 0.0)           # arrows start at origin
    # direction preserved: atan2(q, d) = atan2(4, 3)
    assert math.atan2(yi[1], xi[1]) == pytest.approx(math.atan2(4.0, 3.0))
    assert "5.0" in polar.i_label.toPlainText()   # |I| = 5 A
    assert "53" in polar.i_label.toPlainText()    # angle ~53.1 deg
    xv, yv = polar.v_arrow.getData()
    assert yv[1] == pytest.approx(0.0, abs=1e-9)  # V along +d
    assert "1.0" in polar.v_label.toPlainText()


def test_update_from_store_uses_latest_sample(qapp):
    store = TelemetryStore()
    mask = _bit("id") | _bit("iq") | _bit("vd") | _bit("vq")
    # ascending bits: id(7), iq(8), vd(9), vq(10); scales 0.01A / 0.0025V
    payload = vp.build_telemetry(0, mask, 8, [(0, (300, 400, 400, 0))])
    store.add_batch(vp.parse_telemetry(payload))
    polar = PolarDQ()
    polar.update_from(store)
    assert "5.0" in polar.i_label.toPlainText()   # (3,4) A -> 5 A

    # empty store must not crash or draw
    PolarDQ().update_from(TelemetryStore())
