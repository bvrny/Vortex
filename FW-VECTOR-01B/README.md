# FW-VECTOR-01B — Vector Control Board Firmware

STM32G473VET6 firmware for the Vector control board. `FW-VECTOR-01B.ioc` is
the CubeMX project; peripheral/pin/clock changes happen there, never by hand.

## App/ — host-testable modules

All protocol- and logic-level firmware lives in `App/` and builds on the
host, so behavior is tested before touching hardware:

| Module | Role |
|---|---|
| `vx_device` | Command handler + state machine (PROTOCOL.md, mirrors SimDevice) |
| `vx_param_store` | Parameter table over generated metadata; NV blob |
| `vx_nv_store` | Ping-pong flash record store (power-loss safe) |
| `vx_protection` | OCP/OVP comparator DAC codes, reject-not-clamp backstop |
| `vx_motor_id` | R/L/flux identification math, PI gain design |
| `vx_telemetry` | Telemetry batch payload builder |
| `vx_usb_tx` / `vx_spsc` | CDC TX batching with ZLP; SPSC byte ring |
| `vx_heartbeat` | Host heartbeat watchdog (200 ms disarm rule) |
| `vx_sensor_iface` | Hall-interpolation sensor abstraction |

## Host tests

```bash
cmake -B build && cmake --build build && ctest --test-dir build
```

## Target integration (pending)

CubeMX-generated code goes in this folder; wire `App/` in from USER CODE
guards only: USB CDC RX -> `vp_decoder_feed` -> `vx_device_handle_frame`;
TX-complete -> `vx_usb_tx_next`; 1 ms tick -> `vx_device_tick`; control task
consumes `vx_device_t` flags (setpoint, motor_id_active, scope trigger).
Safety stays hardware-first: TIM1 BRK + comparators are independent of all
of this.
