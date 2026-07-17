"""Numpy ring buffers holding telemetry history for the plots."""

from __future__ import annotations

import numpy as np

import vortex_protocol as vp


class ChannelRing:
    def __init__(self, capacity: int):
        self.capacity = capacity
        self._t = np.zeros(capacity)
        self._v = np.zeros(capacity)
        self._n = 0  # total samples ever appended

    def append(self, t: np.ndarray, v: np.ndarray) -> None:
        k = len(t)
        if k > self.capacity:  # only the newest fit anyway
            t, v, k = t[-self.capacity:], v[-self.capacity:], self.capacity
        idx = (self._n + np.arange(k)) % self.capacity
        self._t[idx] = t
        self._v[idx] = v
        self._n += k

    def window(self, n: int | None = None):
        """Latest n samples (all if None) as (t, v), chronological."""
        avail = min(self._n, self.capacity)
        n = avail if n is None else min(n, avail)
        idx = (self._n - n + np.arange(n)) % self.capacity
        return self._t[idx], self._v[idx]


class TelemetryStore:
    """Routes TelemetryBatch samples into per-channel physical-unit rings."""

    def __init__(self, capacity: int = 100_000):
        self.rings = {c.name: ChannelRing(capacity) for c in vp.CHANNELS}

    def add_batch(self, batch: vp.TelemetryBatch) -> None:
        if not batch.samples:
            return
        chans = vp.active_channels(batch.channel_mask)
        t = (batch.base_timestamp_us +
             np.array([off for off, _ in batch.samples], dtype=np.float64)) / 1e6
        vals = np.array([v for _, v in batch.samples], dtype=np.float64)
        for j, ch in enumerate(chans):
            self.rings[ch.name].append(t, vals[:, j] * ch.scale)

    def window(self, name: str, n: int | None = None):
        return self.rings[name].window(n)
