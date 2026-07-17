"""Make the generated protocol module importable by the test suite.

The single source of truth is protocol.yaml; codegen/generate.py emits
generated/vortex_protocol.py. Tests import the *generated* artifact so they
verify exactly what firmware and app consume.
"""

import sys
from pathlib import Path

GENERATED_DIR = Path(__file__).resolve().parents[2] / "generated"
sys.path.insert(0, str(GENERATED_DIR))
