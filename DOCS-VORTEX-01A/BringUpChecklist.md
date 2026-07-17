# Vortex HIL Bring-Up Checklist

Commissioning order for a new Vector + Flux board pair. Do not skip steps;
each stage assumes the previous one passed. Bench supply with current limit,
scope, and a known-good BLDC motor required.

## 1. Vector board alone (no Flux, no motor)

- [ ] Visual inspection; no shorts across rails (meter, unpowered).
- [ ] Power via bench supply at 24 V, current limit 200 mA.
- [ ] Rails: 12 V (LM5013), 5 V (TPS62913), 3.3 V digital (TL1963A),
      3.3 V analog (TPS7A2033) — all within ±3 %.
- [ ] Flash firmware; verify SWD attach and boot to INIT/STANDBY.
- [ ] USB enumerates as CDC (VID 0483 / PID 5740); `HELLO` returns
      protocol 1.x from the app or `python -m serial.tools.miniterm`.
- [ ] Heartbeat: connect app, confirm state STANDBY, no faults.
- [ ] PARAM round-trip: write, SAVE, power-cycle, verify LOAD restores.

## 2. Vector + Flux, no motor, bus at 24 V

- [ ] Precharge: bus ramps, precharge relay/bypass engages, state reaches
      STANDBY (no PRECHARGE timeout fault).
- [ ] Gate driver enable defaults OFF; verify all six gates low at standby.
- [ ] Current-sense offsets: telemetry ia/ib/ic within ±0.5 A of zero.
- [ ] Vbus telemetry matches bench supply within 2 %.
- [ ] OCP comparator: inject DAC test level (PROTECTION_SET floor 10 A),
      verify TIM1 BRK trips and OVERCURRENT latches. Restore setpoint.
- [ ] OVP path: raise supply toward 63 V — brake chopper regulates at
      63 V; comparator backstop never fires below 65.5 V setting.

## 3. Motor attached, low bus voltage

- [ ] Hall sanity: rotate shaft by hand; sector telemetry cycles 1–6, no
      HALL_FAULT.
- [ ] Motor identification (MOTOR_ID_START): R, Ld, Lq, flux plausible for
      the motor datasheet; gains recomputed.
- [ ] ARM at zero setpoint; phase currents stay ~0; DISARM works.
- [ ] Low torque setpoint (2–5 % of rating): smooth rotation both signs of
      setpoint; phase currents sinusoidal on scope.
- [ ] STOP (Space bar) from RUNNING: PWM off within one control cycle.
- [ ] Heartbeat loss: kill the app while ARMED — device disarms and
      latches HEARTBEAT_LOSS within 200 ms.

## 4. Power envelope

- [ ] Step to 48 V bus; repeat OCP/OVP checks at operating voltage.
- [ ] Sustained load run; temp_inv/temp_motor telemetry rises sanely and
      OVERTEMP limits trip when configured low.
- [ ] Regeneration test: decelerate under load, brake chopper holds bus
      below 63.5 V.

Record serials, measured rail voltages, sense offsets, and motor-ID results
in the build log before the board ships.
