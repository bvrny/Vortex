"""PTY transport: exposes a SimDevice as a serial-port-like /dev/pts node."""

from __future__ import annotations

import os
import selectors
import time
import tty

POLL_S = 0.01


def serve(master_fd: int, dev, stop=None) -> None:
    """Pump bytes between the pty master and the device until stop is set."""
    tty.setraw(master_fd)
    sel = selectors.DefaultSelector()
    sel.register(master_fd, selectors.EVENT_READ)
    last = time.monotonic()
    while stop is None or not stop.is_set():
        events = sel.select(timeout=POLL_S)
        for _key, _mask in events:
            try:
                data = os.read(master_fd, 4096)
            except OSError:  # peer closed
                return
            if data:
                os.write(master_fd, dev.feed(data))
        now = time.monotonic()
        out = dev.tick(now - last)
        last = now
        if out:
            os.write(master_fd, out)
