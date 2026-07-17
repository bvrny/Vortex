"""Make the generated protocol module and the simulator package importable."""

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
for p in (_REPO / "PROTO-VORTEX-01A" / "generated", _REPO / "APP-VORTEX"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))
