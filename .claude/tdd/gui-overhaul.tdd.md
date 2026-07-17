# TDD Evidence — APP-VORTEX GUI Overhaul (5 phases)

**Source plan**: approved inline via `/ecc:plan` (2026-07-17); journeys written
per phase in each test file's docstring.
**Runner**: `source .venv/bin/activate && python -m pytest APP-VORTEX/tests`
(offscreen Qt). Coverage: `--cov=vortex_app`.

## RED/GREEN checkpoints (branch `main`)

| Phase | RED commit | GREEN commit |
|---|---|---|
| 1 foundation | 0ba4588 (5 tests, ImportError: `vortex_app.theme`) | 0723d29 (44 pass) |
| 2 params | 5dcc0a8 (ImportError: `widgets.params`) | params GREEN commit (51 pass) |
| 3 plots/dash | test commit (ImportError: `csvlog`/`widgets.plots`) | plots GREEN commit (56 pass) |
| 4 tuning | test commit (ImportError: `widgets.tuning`) | tuning GREEN commit (62 pass) |
| 5 console | test commit (ImportError: `widgets.console`) | console GREEN commit (71 pass) |

Each RED was an executed pytest run failing on the intended missing module
(collection ImportError = compile-time RED for the unimplemented feature).
Each GREEN reran the full `APP-VORTEX/tests` suite.

## What the passing tests guarantee

| # | Guarantee | Test | Result |
|---|---|---|---|
| 1 | Dark palette applied app-wide; every telemetry channel has a theme color | `test_ui_foundation.py` | PASS |
| 2 | Window = toolbar safety controls + Dashboard/Tuning/Parameters/Console tabs | `test_ui_foundation.py::test_window_has_tabbed_layout` | PASS |
| 3 | Serial ports enumerated as a list (no pyserial → []) | `test_ui_foundation.py::test_list_serial_ports_returns_list` | PASS |
| 4 | All 26 params shown grouped; RW rows editable in place; editors carry metadata bounds; enums become combos | `test_params_panel.py` | PASS |
| 5 | Writes hit the device, mark differs-from-default and unsaved-to-flash until Save | `test_params_panel.py::test_write_updates_device_and_marks_state` | PASS |
| 6 | Profile JSON export/diff/apply round-trips | `test_params_panel.py::test_profile_roundtrip_and_diff` | PASS |
| 7 | Channel checkboxes ⇄ telemetry mask bits; changes emit for stream restart | `test_plots_dashboard.py::test_channel_panel_mask_roundtrip` | PASS |
| 8 | Plots group one row per unit; pause freezes curves | `test_plots_dashboard.py` | PASS |
| 9 | CSV log rows are physical units at telemetry scale | `test_plots_dashboard.py::test_csv_logger_writes_scaled_rows` | PASS |
| 10 | Scope chunked read reassembles a parseable 128-sample capture; read-before-capture is BAD_STATE not a crash | `test_tuning.py::test_scope_helpers_chunked_roundtrip` | PASS |
| 11 | Bandwidth knob writes kp=L·ω, ki=R·ω (matches protocol.yaml defaults) | `test_tuning.py` | PASS |
| 12 | Step capture applies the setpoint and returns the capture batch | `test_tuning.py::test_run_step_capture_returns_batch` | PASS |
| 13 | Motor-ID progress/result/failure frames tracked; wizard shows results | `test_tuning.py` | PASS |
| 14 | Console commands (arm/stop/sp/param/fault/hb/dfu) act on the device; errors are messages, never exceptions | `test_console.py` | PASS |
| 15 | Command history ↑/↓ semantics; event log records state/fault *changes* only | `test_console.py` | PASS |
| 16 | Legacy flow intact: connect → arm → stream → stop (smoke) | `test_gui_smoke.py` | PASS |

## Coverage

`python -m pytest APP-VORTEX/tests --cov=vortex_app`: **85 % total** (73 tests).
Gaps: `main.py` 76 % (Qt slots needing dialogs: file pickers, connect-error
box), `__main__.py` (entry stub), console/params GUI event filters. All
uncovered paths are interactive-dialog glue, not device-facing logic.

## Test corrections during the run (documented per TDD rules)

- `test_event_log_records_changes_only`: original test passed
  `int(vp.Fault.OVERCURRENT)` as a mask, but `Fault` members are bit indices
  (== 0). Test fixed to `1 << vp.Fault.OVERCURRENT`; implementation unchanged.
- Console integer-param write initially failed GREEN (`struct.error`), fixed
  in implementation by coercing non-F32 values to int.

## Manual end-to-end

Offscreen scripted launch: apply theme → MainWindow → connect to in-process
sim → ARM → poll telemetry → heartbeat shows ARMED → scope capture returns
128 samples → STOP → disconnect. Output: `manual end-to-end launch check OK`.
