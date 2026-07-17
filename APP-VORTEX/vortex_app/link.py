"""DeviceLink: synchronous protocol client over a pluggable transport.

Transports expose non-blocking write(bytes) / read() -> bytes.
"""

from __future__ import annotations

import struct
import time

import vortex_protocol as vp


class LinkTimeout(TimeoutError):
    pass


class SimTransport:
    """In-process transport wrapping a simulator.SimDevice."""

    def __init__(self, dev):
        self.dev = dev
        self._rx = bytearray()

    def write(self, data: bytes) -> None:
        self._rx += self.dev.feed(data)

    def read(self) -> bytes:
        out = bytes(self._rx)
        self._rx.clear()
        return out

    def tick(self, dt: float) -> None:
        """Advance simulated time (telemetry, watchdog, motor-ID)."""
        self._rx += self.dev.tick(dt)

    def close(self) -> None:
        pass


class SerialTransport:
    """pyserial transport for real hardware or the pty simulator."""

    def __init__(self, port: str, baud: int = 115200):
        import serial  # deferred: keeps headless tests free of pyserial

        self.ser = serial.Serial(port, baud, timeout=0)

    def write(self, data: bytes) -> None:
        self.ser.write(data)

    def read(self) -> bytes:
        return self.ser.read(4096)

    def close(self) -> None:
        self.ser.close()


class DeviceLink:
    def __init__(self, transport, timeout: float = 1.0):
        self.transport = transport
        self.timeout = timeout
        self._dec = vp.WireDecoder()
        self._seq = 0
        self._unsolicited: list[vp.Frame] = []

    def _pump(self) -> list[vp.Frame]:
        data = self.transport.read()
        return self._dec.feed(data) if data else []

    def request(self, cmd, payload: bytes = b"", timeout: float | None = None):
        """Send one request; returns (Status, payload-after-status)."""
        self._seq = (self._seq + 1) & 0xFF
        seq = self._seq
        self.transport.write(vp.encode_wire(vp.Frame(cmd=cmd, payload=payload, seq=seq)))
        deadline = time.monotonic() + (timeout or self.timeout)
        while time.monotonic() < deadline:
            for f in self._pump():
                if f.flags & vp.FLAG_RESPONSE:
                    if f.cmd == cmd and f.seq == seq:
                        return vp.Status(f.payload[0]), f.payload[1:]
                    continue  # stale response: drop
                self._unsolicited.append(f)
            time.sleep(0.001)
        raise LinkTimeout(f"no response to {cmd!r} within {timeout or self.timeout}s")

    def poll(self) -> list[vp.Frame]:
        """Unsolicited device->host frames (telemetry, motor-ID progress)."""
        for f in self._pump():
            if not f.flags & vp.FLAG_RESPONSE:
                self._unsolicited.append(f)
        out = self._unsolicited
        self._unsolicited = []
        return out

    # ------------------------------------------------------------- helpers

    def read_param(self, name: str):
        meta = vp.PARAM_BY_NAME[name]
        status, rest = self.request(vp.Cmd.PARAM_READ, struct.pack("<H", meta.id))
        if status != vp.Status.OK:
            raise LinkTimeout(f"PARAM_READ {name}: {status.name}")
        return vp.decode_param_value(meta, rest[2:])

    def write_param(self, name: str, value) -> vp.Status:
        meta = vp.PARAM_BY_NAME[name]
        payload = struct.pack("<H", meta.id) + vp.encode_param_value(meta, value)
        return self.request(vp.Cmd.PARAM_WRITE, payload)[0]

    def heartbeat(self):
        """Returns (DeviceState, active fault mask)."""
        status, rest = self.request(vp.Cmd.HEARTBEAT)
        if status != vp.Status.OK:
            raise LinkTimeout(f"HEARTBEAT: {status.name}")
        state, faults = struct.unpack("<BI", rest)
        return vp.DeviceState(state), faults

    def setpoint(self, mode: vp.SetpointMode, value: float) -> vp.Status:
        return self.request(vp.Cmd.SETPOINT, struct.pack("<Bf", int(mode), value))[0]

    def close(self) -> None:
        self.transport.close()
