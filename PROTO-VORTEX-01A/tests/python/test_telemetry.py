"""Telemetry batch payload:
[base_timestamp_us u32][channel_mask u32][n_samples u16][decimation u16]
then per sample: [t_offset_us u16][int16 x popcount(mask), in ascending bit order]
All little-endian.
"""

import pytest

import vortex_protocol as vp


def _mask(*names: str) -> int:
    by_name = {c.name: c.bit for c in vp.CHANNELS}
    m = 0
    for n in names:
        m |= 1 << by_name[n]
    return m


def test_telemetry_roundtrip():
    mask = _mask("ia", "ib", "ic", "vbus")
    samples = [(0, (100, -100, 0, 24000)), (25, (110, -90, -20, 24010))]
    payload = vp.build_telemetry(base_timestamp_us=123456, channel_mask=mask,
                                 decimation=8, samples=samples)
    batch = vp.parse_telemetry(payload)
    assert batch.base_timestamp_us == 123456
    assert batch.channel_mask == mask
    assert batch.decimation == 8
    assert batch.samples == samples


def test_telemetry_sample_size_matches_mask_popcount():
    mask = _mask("ia", "iq")
    payload = vp.build_telemetry(0, mask, 1, [(0, (1, 2))])
    # header 12 bytes + 1 sample * (2 + 2*2) bytes
    assert len(payload) == 12 + 6


def test_telemetry_rejects_wrong_sample_width():
    mask = _mask("ia", "ib")
    with pytest.raises(ValueError):
        vp.build_telemetry(0, mask, 1, [(0, (1, 2, 3))])


def test_telemetry_parse_rejects_truncated_payload():
    mask = _mask("ia")
    payload = vp.build_telemetry(0, mask, 1, [(0, (5,))])
    with pytest.raises(ValueError):
        vp.parse_telemetry(payload[:-1])


def test_bandwidth_fits_usb_fs_budget():
    # 7 channels at 5 kHz: (2 + 7*2) B/sample = 16 B * 5000 = 80 kB/s,
    # well under the ~600 kB/s practical CDC throughput floor.
    per_sample = 2 + 7 * 2
    assert per_sample * 5000 < 600_000
