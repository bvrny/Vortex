"""PTY transport smoke test: the simulator answers over a real pty."""

import os
import pty
import selectors
import struct
import threading
import time
import tty

import vortex_protocol as vp
from simulator import SimDevice
from simulator.transport import serve

TIMEOUT_S = 5.0


def _rpc_over_fd(fd, cmd, payload=b"", seq=1):
    os.write(fd, vp.encode_wire(vp.Frame(cmd=cmd, payload=payload, seq=seq)))
    dec = vp.WireDecoder()
    sel = selectors.DefaultSelector()
    sel.register(fd, selectors.EVENT_READ)
    deadline = time.monotonic() + TIMEOUT_S
    while time.monotonic() < deadline:
        if sel.select(timeout=0.05):
            for f in dec.feed(os.read(fd, 4096)):
                if f.flags & vp.FLAG_RESPONSE and f.cmd == cmd:
                    return vp.Status(f.payload[0]), f.payload[1:]
    raise TimeoutError("no response over pty")


def test_hello_and_telemetry_over_pty():
    master, slave = pty.openpty()
    tty.setraw(slave)
    stop = threading.Event()
    t = threading.Thread(target=serve, args=(master, SimDevice(), stop), daemon=True)
    t.start()
    try:
        status, rest = _rpc_over_fd(slave, vp.Cmd.HELLO)
        assert status == vp.Status.OK
        assert rest[0] == vp.PROTOCOL_VERSION_MAJOR

        status, _ = _rpc_over_fd(slave, vp.Cmd.TELEMETRY_START,
                                 struct.pack("<IH", 0x1, 8), seq=2)
        assert status == vp.Status.OK
        dec = vp.WireDecoder()
        deadline = time.monotonic() + TIMEOUT_S
        got = []
        sel = selectors.DefaultSelector()
        sel.register(slave, selectors.EVENT_READ)
        while not got and time.monotonic() < deadline:
            if sel.select(timeout=0.05):
                got = [f for f in dec.feed(os.read(slave, 4096))
                       if f.cmd == vp.Cmd.TELEMETRY_DATA]
        assert got, "no telemetry over pty"
        vp.parse_telemetry(got[0].payload)  # decodes cleanly
    finally:
        stop.set()
        t.join(timeout=2)
        os.close(slave)
        os.close(master)
