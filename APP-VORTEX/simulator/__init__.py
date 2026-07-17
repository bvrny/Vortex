"""Vortex device simulator — behaves like FW-VECTOR-01B over the wire protocol."""

import sys
from pathlib import Path

# Monorepo path bootstrap so `import vortex_protocol` works from anywhere.
_GEN = Path(__file__).resolve().parents[2] / "PROTO-VORTEX-01A" / "generated"
if str(_GEN) not in sys.path:
    sys.path.insert(0, str(_GEN))

from simulator.device import SimDevice  # noqa: E402

__all__ = ["SimDevice"]
