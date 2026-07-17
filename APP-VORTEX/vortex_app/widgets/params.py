"""Parameter panel: metadata-driven tree with in-place editing.

Editing goes through ParamDelegate (spinbox/combo built from generated
metadata, bounds enforced by the editor before the device re-checks them).
Tracks unsaved-to-flash (NV) writes and differs-from-default per param.
Profiles are JSON files {param_name: value} with a diff preview.
"""

from __future__ import annotations

import json
from pathlib import Path

import vortex_protocol as vp
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (QComboBox, QDoubleSpinBox, QAbstractSpinBox,
                               QLineEdit, QSpinBox, QStyledItemDelegate,
                               QTreeWidget, QTreeWidgetItem, QVBoxLayout,
                               QWidget)

from vortex_app import theme
from vortex_app.link import LinkTimeout


def _fmt(meta, value) -> str:
    if meta.enum_values is not None:
        return meta.enum_values[int(value)]
    return f"{value:.6g}" if isinstance(value, float) else str(value)


class _NoEditDelegate(QStyledItemDelegate):
    def createEditor(self, parent, option, index):  # noqa: ARG002
        return None


class ParamDelegate(QStyledItemDelegate):
    """Builds the right editor for the value column from param metadata."""

    def __init__(self, panel: "ParamPanel"):
        super().__init__(panel)
        self.panel = panel

    def _meta(self, index):
        name = index.sibling(index.row(), 0).data(Qt.UserRole)
        return vp.PARAM_BY_NAME.get(name) if name else None

    def createEditor(self, parent, option, index):  # noqa: ARG002
        meta = self._meta(index)
        if meta is None:
            return None
        if meta.enum_values is not None:
            combo = QComboBox(parent)
            combo.addItems(list(meta.enum_values))
            return combo
        if meta.type == vp.ParamType.F32:
            spin = QDoubleSpinBox(parent, minimum=meta.min, maximum=meta.max,
                                  decimals=6)
            spin.setStepType(QAbstractSpinBox.AdaptiveDecimalStepType)
            spin.setSuffix(f" {meta.unit}" if meta.unit else "")
            return spin
        spin = QSpinBox(parent, minimum=int(meta.min), maximum=int(meta.max))
        spin.setSuffix(f" {meta.unit}" if meta.unit else "")
        return spin

    def setEditorData(self, editor, index):
        meta = self._meta(index)
        value = self.panel.value(meta.name)
        if value is None:
            return
        if isinstance(editor, QComboBox):
            editor.setCurrentIndex(int(value))
        elif isinstance(editor, QDoubleSpinBox):
            editor.setValue(float(value))
        else:
            editor.setValue(int(value))

    def setModelData(self, editor, model, index):  # noqa: ARG002
        meta = self._meta(index)
        if isinstance(editor, QComboBox):
            value = editor.currentIndex()
        elif isinstance(editor, QDoubleSpinBox):
            value = editor.value()
        else:
            value = int(editor.value())
        self.panel.write_value(meta.name, value)


class ParamPanel(QWidget):
    """Filter box + grouped parameter tree with editing and state colors."""

    save_dirty_changed = Signal(bool)
    status_message = Signal(str)

    def __init__(self, link_getter):
        super().__init__()
        self.link = link_getter                     # callable -> DeviceLink|None
        self._values: dict[str, float | int] = {}
        self._dirty_nv: set[str] = set()
        self._items: dict[str, QTreeWidgetItem] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.filter_edit = QLineEdit(placeholderText="Filter parameters…")
        self.filter_edit.textChanged.connect(self.set_filter)
        layout.addWidget(self.filter_edit)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Parameter", "Value", "Unit"])
        self.tree.setColumnWidth(0, 220)
        self.tree.setAlternatingRowColors(True)
        self.tree.setEditTriggers(QTreeWidget.DoubleClicked
                                  | QTreeWidget.SelectedClicked)
        self.tree.setItemDelegateForColumn(0, _NoEditDelegate(self.tree))
        self.tree.setItemDelegateForColumn(1, ParamDelegate(self))
        self.tree.setItemDelegateForColumn(2, _NoEditDelegate(self.tree))
        layout.addWidget(self.tree, 1)

    # ------------------------------------------------------------- state

    @property
    def save_dirty(self) -> bool:
        return bool(self._dirty_nv)

    def mark_saved(self) -> None:
        self._dirty_nv.clear()
        self.save_dirty_changed.emit(False)

    def value(self, name: str):
        return self._values.get(name)

    def differs_from_default(self, name: str) -> bool:
        meta = vp.PARAM_BY_NAME[name]
        value = self._values.get(name)
        return value is not None and value != meta.default

    # ----------------------------------------------------------- populate

    def refresh(self) -> None:
        link = self.link()
        if link is None:
            return
        self.tree.clear()
        self._items.clear()
        groups: dict[str, QTreeWidgetItem] = {}
        for meta in sorted(vp.PARAMS.values(), key=lambda m: m.id):
            group = groups.get(meta.group)
            if group is None:
                group = groups[meta.group] = QTreeWidgetItem(self.tree,
                                                             [meta.group])
                group.setExpanded(True)
            try:
                self._values[meta.name] = link.read_param(meta.name)
            except LinkTimeout:
                self._values.pop(meta.name, None)
            item = QTreeWidgetItem(group, ["", "", meta.unit])
            item.setText(0, meta.name.split(".", 1)[1])
            item.setData(0, Qt.UserRole, meta.name)
            storage = "flash (NV)" if meta.storage == "NV" else "RAM only"
            item.setToolTip(0, f"{meta.name}\n{meta.min:g} .. {meta.max:g} "
                               f"{meta.unit}\n{storage}, {meta.access}")
            if meta.access == "RW":
                item.setFlags(item.flags() | Qt.ItemIsEditable)
            self._items[meta.name] = item
            self._update_item(meta.name)
        self.set_filter(self.filter_edit.text())

    def _update_item(self, name: str) -> None:
        item = self._items.get(name)
        value = self._values.get(name)
        if item is None:
            return
        meta = vp.PARAM_BY_NAME[name]
        item.setText(1, "?" if value is None else _fmt(meta, value))
        color = theme.ACCENT if self.differs_from_default(name) else theme.FG
        item.setForeground(1, QBrush(QColor(color)))

    # ------------------------------------------------------------ editing

    def write_value(self, name: str, value) -> vp.Status:
        link = self.link()
        if link is None:
            return vp.Status.NACK_BAD_STATE
        try:
            status = link.write_param(name, value)
        except LinkTimeout as e:
            self.status_message.emit(str(e))
            return vp.Status.NACK_BAD_STATE
        if status == vp.Status.OK:
            self._values[name] = link.read_param(name)
            meta = vp.PARAM_BY_NAME[name]
            if meta.storage == "NV":
                self._dirty_nv.add(name)
                self.save_dirty_changed.emit(True)
        else:
            self.status_message.emit(f"PARAM_WRITE {name}: {status.name}")
        self._update_item(name)
        return status

    # ------------------------------------------------------------- filter

    def set_filter(self, text: str) -> None:
        text = text.strip().lower()
        for name, item in self._items.items():
            item.setHidden(bool(text) and text not in name.lower())
        for g in range(self.tree.topLevelItemCount()):
            group = self.tree.topLevelItem(g)
            group.setHidden(all(group.child(i).isHidden()
                                for i in range(group.childCount())))

    # ------------------------------------------------------------ profiles

    def export_profile(self, path: str | Path) -> None:
        rw = {name: value for name, value in self._values.items()
              if vp.PARAM_BY_NAME[name].access == "RW"}
        Path(path).write_text(json.dumps(rw, indent=2, sort_keys=True))

    def diff_profile(self, path: str | Path) -> list[tuple]:
        blob = json.loads(Path(path).read_text())
        diff = []
        for name, new in blob.items():
            meta = vp.PARAM_BY_NAME.get(name)
            if meta is None or meta.access != "RW":
                continue                       # unknown/foreign entry: skip
            current = self._values.get(name)
            if current != new:
                diff.append((name, current, new))
        return diff

    def apply_profile(self, path: str | Path) -> list[tuple]:
        """Write every differing value; returns entries that failed."""
        failed = []
        for name, current, new in self.diff_profile(path):
            if self.write_value(name, new) != vp.Status.OK:
                failed.append((name, current, new))
        return failed
