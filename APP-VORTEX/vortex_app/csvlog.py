"""CSV recorder for the live telemetry stream (physical units)."""

from __future__ import annotations

import csv
from pathlib import Path

import vortex_protocol as vp


class CsvLogger:
    """Writes `t,<channels>` rows for every sample of the chosen mask."""

    def __init__(self, path: str | Path, mask: int):
        self.channels = vp.active_channels(mask)
        self._file = open(path, "w", newline="")
        self._writer = csv.writer(self._file)
        self._writer.writerow(["t"] + [c.name for c in self.channels])
        self.rows_written = 0

    def add_batch(self, batch: vp.TelemetryBatch) -> None:
        chans = vp.active_channels(batch.channel_mask)
        for off, raw in batch.samples:
            t = (batch.base_timestamp_us + off) / 1e6
            by_name = {c.name: v * c.scale for c, v in zip(chans, raw)}
            self._writer.writerow(
                [f"{t:.6f}"] + [f"{by_name[c.name]:g}" if c.name in by_name
                                else "" for c in self.channels])
            self.rows_written += 1

    def close(self) -> None:
        self._file.close()
