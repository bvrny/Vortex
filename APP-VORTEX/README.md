# APP-VORTEX — Desktop Control App + Device Simulator

PySide6 desktop tool for tuning and monitoring the Vortex motor driver, plus a
protocol-complete device simulator used for development and tests without
hardware. Both implement `PROTO-VORTEX-01A/PROTOCOL.md` via the generated
`vortex_protocol` module (single source of truth: `protocol.yaml`).

## Stack

- **PySide6 + pyqtgraph** — cross-platform GUI with real-time plotting.
- **numpy** — telemetry ring buffers (`vortex_app/rings.py`).
- **pyserial** — CDC-ACM transport to real hardware.
- Simulator needs none of the above: pure stdlib + generated protocol.

## Run

```bash
source ../.venv/bin/activate
python -m vortex_app                 # GUI (connect to simulator in-process
                                     # or to a serial port)
python -m simulator                  # simulator on a PTY; prints the port
```

Space bar = emergency STOP. ARM/DISARM, setpoint, parameter tree,
fault banner, motor identification, and three live plots are in the main
window.

## Test

```bash
python -m pytest tests ../PROTO-VORTEX-01A/tests/python
```

## Package

```bash
pip install pyinstaller
./packaging/build-linux.sh           # Linux onedir -> dist/vortex-app/
packaging\build-windows.ps1          # Windows onefile -> dist\vortex-app.exe
```

Linux device permissions: `packaging/99-vortex.rules` (see file header).

## CI matrix

| Job | Platform | Steps |
|---|---|---|
| protocol | ubuntu-latest | `python codegen/generate.py --check`, pytest PROTO tests, gcc + run `tests/c/test_protocol.c` |
| firmware-host | ubuntu-latest | `cmake -B build FW-VECTOR-01B && ctest` |
| app | ubuntu-latest, windows-latest | pytest APP-VORTEX tests (Qt offscreen: `QT_QPA_PLATFORM=offscreen`) |
| package | tag only | packaging scripts above |
