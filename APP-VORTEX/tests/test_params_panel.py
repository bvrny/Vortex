"""Phase 2 parameter panel: in-place editing, dirty/default state, profiles.

User journeys:
- As a tuner, I want to edit parameters directly in the tree with proper
  spinboxes/combos showing bounds and units, so editing feels safe and obvious.
- As a tuner, I want to see which values differ from defaults and which are
  unsaved to flash, so I know the device's config state at a glance.
- As a user, I want to save/load parameter profiles as files and preview the
  diff before applying.
"""

import json
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

import vortex_protocol as vp                                  # noqa: E402
from PySide6.QtCore import Qt                                 # noqa: E402
from PySide6.QtWidgets import (QApplication, QComboBox,       # noqa: E402
                               QDoubleSpinBox)

from simulator import SimDevice                               # noqa: E402
from vortex_app.link import DeviceLink, SimTransport          # noqa: E402
from vortex_app.widgets.params import ParamDelegate, ParamPanel  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture()
def panel(qapp):
    link = DeviceLink(SimTransport(SimDevice()))
    p = ParamPanel(lambda: link)
    p.refresh()
    return p


def _item(panel, name):
    for g in range(panel.tree.topLevelItemCount()):
        group = panel.tree.topLevelItem(g)
        for i in range(group.childCount()):
            item = group.child(i)
            if item.data(0, Qt.UserRole) == name:
                return item
    return None


def test_all_params_present_and_grouped(panel):
    names = {m.name for m in vp.PARAMS.values()}
    found = {_item(panel, n) is not None for n in names}
    assert found == {True}
    assert panel.tree.topLevelItemCount() == len({m.group for m in vp.PARAMS.values()})


def test_rw_params_editable_in_place(panel):
    item = _item(panel, "motor.pole_pairs")
    assert item.flags() & Qt.ItemIsEditable


def test_delegate_creates_bounded_editor(panel, qapp):
    delegate = panel.tree.itemDelegateForColumn(1)
    assert isinstance(delegate, ParamDelegate)
    item = _item(panel, "motor.r_phase")           # f32 0.0005..2.0
    index = panel.tree.indexFromItem(item, 1)
    editor = delegate.createEditor(panel.tree, None, index)
    assert isinstance(editor, QDoubleSpinBox)
    meta = vp.PARAM_BY_NAME["motor.r_phase"]
    assert editor.minimum() == pytest.approx(meta.min)
    assert editor.maximum() == pytest.approx(meta.max)


def test_delegate_creates_combo_for_enum(panel, qapp):
    delegate = panel.tree.itemDelegateForColumn(1)
    item = _item(panel, "sensor.mode")
    index = panel.tree.indexFromItem(item, 1)
    editor = delegate.createEditor(panel.tree, None, index)
    assert isinstance(editor, QComboBox)
    assert editor.count() == len(vp.PARAM_BY_NAME["sensor.mode"].enum_values)


def test_write_updates_device_and_marks_state(panel):
    assert panel.write_value("motor.pole_pairs", 14) == vp.Status.OK
    assert panel.link().read_param("motor.pole_pairs") == 14
    item = _item(panel, "motor.pole_pairs")
    assert panel.differs_from_default("motor.pole_pairs")
    assert "14" in item.text(1)
    # NV param written -> unsaved-to-flash until mark_saved()
    assert panel.save_dirty
    panel.mark_saved()
    assert not panel.save_dirty


def test_filter_hides_non_matching(panel):
    panel.set_filter("kp")
    assert not _item(panel, "iloop.kp").isHidden()
    assert _item(panel, "motor.r_phase").isHidden()
    panel.set_filter("")
    assert not _item(panel, "motor.r_phase").isHidden()


def test_profile_roundtrip_and_diff(panel, tmp_path):
    path = tmp_path / "profile.json"
    panel.write_value("motor.pole_pairs", 14)
    panel.export_profile(path)
    blob = json.loads(path.read_text())
    assert blob["motor.pole_pairs"] == 14

    panel.write_value("motor.pole_pairs", 7)       # change it back
    diff = panel.diff_profile(path)
    assert ("motor.pole_pairs", 7, 14) in diff

    panel.apply_profile(path)
    assert panel.link().read_param("motor.pole_pairs") == 14
