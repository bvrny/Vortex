"""Protocol console with command history + timestamped event log.

Typed commands map to protocol requests (the CLI-tuning workflow, adapted
to our framed protocol). Errors come back as messages, never exceptions.
"""

from __future__ import annotations

import struct
import time

import vortex_protocol as vp
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QHBoxLayout, QLineEdit, QPlainTextEdit,
                               QPushButton, QVBoxLayout, QWidget)

from vortex_app.link import LinkTimeout

HELP = """commands:
  help                       this list
  arm | disarm | stop        state control (stop always honored)
  sp <torque|speed> <value>  setpoint
  param <name>               read one parameter
  param <name> <value>       write one parameter
  fault                      read active/latched fault masks
  fault clear                clear latched faults
  hb                         one heartbeat (state + faults)
  dfu                        reboot into the ROM bootloader"""

_SIMPLE = {"arm": vp.Cmd.ARM, "disarm": vp.Cmd.DISARM, "stop": vp.Cmd.STOP}


class ConsoleLogic:
    """Parses and executes console commands against the DeviceLink."""

    def __init__(self, link_getter):
        self.link = link_getter

    def execute(self, text: str) -> str:
        parts = text.strip().split()
        if not parts:
            return ""
        if parts[0] == "help":
            return HELP
        link = self.link()
        if link is None:
            return "not connected"
        try:
            return self._dispatch(link, parts)
        except LinkTimeout as e:
            return f"timeout: {e}"

    def _dispatch(self, link, parts) -> str:
        cmd, args = parts[0], parts[1:]
        if cmd in _SIMPLE:
            return link.request(_SIMPLE[cmd])[0].name
        if cmd == "sp":
            if len(args) != 2 or args[0] not in ("torque", "speed"):
                return "usage: sp <torque|speed> <value>"
            try:
                value = float(args[1])
            except ValueError:
                return "usage: sp <torque|speed> <value>"
            mode = (vp.SetpointMode.TORQUE if args[0] == "torque"
                    else vp.SetpointMode.SPEED)
            return link.setpoint(mode, value).name
        if cmd == "param":
            if not args:
                return "usage: param <name> [value]"
            meta = vp.PARAM_BY_NAME.get(args[0])
            if meta is None:
                return f"unknown param: {args[0]}"
            if len(args) == 1:
                value = link.read_param(args[0])
                shown = (meta.enum_values[int(value)]
                         if meta.enum_values is not None else f"{value:g}")
                return f"{args[0]} = {shown} {meta.unit}".rstrip()
            try:
                value = float(args[1])
            except ValueError:
                return "usage: param <name> <numeric value>"
            if meta.type != vp.ParamType.F32:
                value = int(round(value))     # integer wire types
            return link.write_param(args[0], value).name
        if cmd == "fault":
            if args == ["clear"]:
                return link.request(vp.Cmd.FAULT_CLEAR)[0].name
            status, rest = link.request(vp.Cmd.FAULT_READ)
            if status != vp.Status.OK:
                return status.name
            active, latched = struct.unpack("<II", rest)
            return (f"active: {vp.decode_faults(active) or 'none'}  "
                    f"latched: {vp.decode_faults(latched) or 'none'}")
        if cmd == "hb":
            state, faults = link.heartbeat()
            return f"{state.name} faults={vp.decode_faults(faults) or 'none'}"
        if cmd == "dfu":
            return link.request(vp.Cmd.ENTER_DFU)[0].name
        return f"unknown command: {cmd} (try 'help')"


class CommandHistory:
    """Up/down line-edit history with a fresh-line slot at the end."""

    def __init__(self):
        self._items: list[str] = []
        self._cursor = 0

    def add(self, text: str) -> None:
        if text:
            self._items.append(text)
        self._cursor = len(self._items)

    def prev(self) -> str:
        if not self._items:
            return ""
        self._cursor = max(0, self._cursor - 1)
        return self._items[self._cursor]

    def next(self) -> str:
        self._cursor = min(len(self._items), self._cursor + 1)
        return (self._items[self._cursor]
                if self._cursor < len(self._items) else "")


class EventLog:
    """(timestamp, kind, text) entries for state and fault *changes*."""

    def __init__(self):
        self.entries: list[tuple[str, str, str]] = []
        self._state = None
        self._faults = 0

    @staticmethod
    def _ts() -> str:
        return time.strftime("%H:%M:%S")

    def record_state(self, state) -> list[tuple[str, str, str]]:
        if state == self._state:
            return []
        self._state = state
        entry = (self._ts(), "state", f"state -> {state.name}")
        self.entries.append(entry)
        return [entry]

    def record_faults(self, latched: int) -> list[tuple[str, str, str]]:
        if latched == self._faults:
            return []
        self._faults = latched
        names = vp.decode_faults(latched) or ["cleared"]
        entry = (self._ts(), "fault", f"faults: {', '.join(names)}")
        self.entries.append(entry)
        return [entry]


class ConsolePanel(QWidget):
    """Console log + input with history, plus the device event log."""

    def __init__(self, link_getter):
        super().__init__()
        self.logic = ConsoleLogic(link_getter)
        self.history = CommandHistory()
        self.events = EventLog()

        layout = QVBoxLayout(self)
        mono = QFont("monospace")
        self.log = QPlainTextEdit(readOnly=True)
        self.log.setFont(mono)
        row = QHBoxLayout()
        self.input = QLineEdit(placeholderText="type 'help'…")
        self.input.setFont(mono)
        self.input.returnPressed.connect(self._on_enter)
        self.input.installEventFilter(self)
        run_btn = QPushButton("Run")
        run_btn.clicked.connect(self._on_enter)
        row.addWidget(self.input, 1)
        row.addWidget(run_btn)
        layout.addWidget(self.log, 1)
        layout.addLayout(row)

    def eventFilter(self, obj, event):
        if obj is self.input and event.type() == QEvent.KeyPress:
            if event.key() == Qt.Key_Up:
                self.input.setText(self.history.prev())
                return True
            if event.key() == Qt.Key_Down:
                self.input.setText(self.history.next())
                return True
        return super().eventFilter(obj, event)

    def _on_enter(self):
        text = self.input.text().strip()
        if not text:
            return
        self.history.add(text)
        self.input.clear()
        ts = time.strftime("%H:%M:%S")
        self.log.appendPlainText(f"[{ts}] > {text}")
        out = self.logic.execute(text)
        if out:
            self.log.appendPlainText(out)

    def record_status(self, state, latched_faults: int) -> None:
        """Feed heartbeat results; appends event entries on change."""
        for ts, kind, text in (self.events.record_state(state) +
                               self.events.record_faults(latched_faults)):
            self.log.appendPlainText(f"[{ts}] * {text}")
