# PROTO-VORTEX-01A — USB Protocol Definition

`protocol.yaml` is the single source of truth for the firmware/app USB
contract: commands, parameters, telemetry channels, enums, fault bits, and
hardware calibration constants. `PROTOCOL.md` adds the payload byte layouts
and transaction rules that YAML cannot express.

## Codegen

```bash
python codegen/generate.py           # regenerate generated/vortex_protocol.{py,h}
python codegen/generate.py --check   # CI drift check: fails if outputs are stale
```

Never edit `generated/` by hand. Changing any payload layout is a breaking
change: bump `meta.version_major`. Additive changes bump `version_minor`.

## Tests

```bash
python -m pytest tests/python        # codec, params, telemetry, golden vectors
gcc -std=c11 -Wall -Wextra -Igenerated tests/c/test_protocol.c -o /tmp/tp && /tmp/tp
```

Golden vectors keep the Python and C codecs bit-identical.
