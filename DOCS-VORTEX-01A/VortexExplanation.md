# Vortex — BLDC Motor Driver
## Design Specification — Revision 1.0

Vortex is a universal field-oriented BLDC motor driver for 24 V and 48 V battery systems,
rated 2.5 kW on a 24 V pack and 5 kW on a 48 V pack, able to run any BLDC/PMSM motor from
roughly 500 W to 5 kW. Revision 1.0 uses field-oriented control (FOC) with space-vector PWM
(SVPWM), commutated from Hall-effect sensors. Phase voltages are measured for monitoring,
diagnostics, and protection.

---

## 0. Key Specifications

| Parameter | Value | Notes |
|---|---|---|
| Output power, 24 V pack | 2.5 kW peak (inverter side) | Treated as continuous for worst-case design |
| Output power, 48 V pack | 5 kW peak (inverter side) | Treated as continuous for worst-case design |
| Motor power range | 500 W – 5 kW | Any BLDC/PMSM motor in this range |
| Continuous phase current (RMS) | ~125 A (design target) | Derived — see note below |
| Peak phase current | ~175 A | Derived |
| Peak DC bus current | ~135 A | 2.5 kW ÷ 19 V (24 V pack at minimum bus) |
| 24 V battery bus range | 19 V – 30 V | Any pack/chemistry in this window |
| 48 V battery bus range | 39 V – 60 V | Any pack/chemistry in this window |
| Absolute max bus voltage (must survive) | 70 V | Headroom for regen/transients above 60 V (§6) |
| Switching frequency | 40 kHz | Above audible range; within INA240 PWM-rejection limit |
| Control | FOC with SVPWM | §15 |
| Position sensing | Hall-effect sensors | §10 |
| Cooling | Custom water-cooled cold plate | §8 |
| Operating ambient temp | To be set per deployment | Coolant temperature is the governing input (§8) |

**Phase-current derivation.** Phase current scales inversely with bus voltage, so the two
operating points are balanced: **24 V / 2.5 kW at 19 V** → ~132 A bus, **~120 A RMS / ~170 A
peak** per phase; **48 V / 5 kW at 39 V** → ~128 A bus, ~116 A RMS / ~165 A peak (near-full
SVPWM, pf ≈ 0.9). The design target is therefore **~125 A RMS continuous, ~175 A peak**, split
across two paralleled FETs (~60 A RMS each — comfortably within the 200 A @ 100 °C rating). The
binding constraint is heat, not current rating.

A 1.2 kW / 48 V reference motor anchors the low end of the envelope: its commercial controller
is rated 25 A continuous / 35 A for 60 s (battery side). Scaling that to the 5 kW ceiling gives
~105–145 A, consistent with the ~120 A RMS target above.

---

## Feature Set (Revision 1.0)

**Power stage & sensing**

- FOC power stage: three half-bridges, 40 kHz SVPWM
- In-line per-phase current sensing (INA240 + 0.1 mΩ shunt)
- Per-phase voltage sensing (monitoring, phase-loss detection, diagnostics)
- DC bus voltage sensing
- Current-sensor offset/gain auto-zero
- Bus capacitance + commutation-loop decoupling
- Power-stage and motor temperature sensing

**Position sensing**

- Hall-effect sensor interface (FOC angle obtained by Hall interpolation)

**Protection & supervision**

- Hardware fast-trip overcurrent (comparator → TIM1 BRK)
- Overvoltage and undervoltage lockout, configurable trip
- Over-temperature foldback then trip (power stage + motor)
- Regen / brake chopper + TVS ("battery can't accept charge" handling)
- Reverse-polarity and short-to-rail I/O protection
- Pre-charge / inrush limiting
- Phase-loss / motor-disconnect detection
- Overspeed / runaway detection
- ESD / surge protection on every external line
- Communication watchdog (safe disarm on lost link)
- MCU windowed watchdog
- Hardware gate-driver enable / TIM1 BRK defaults OFF (fail-safe)

**Control & commissioning**

- FOC with SVPWM; speed setpoint via cascaded speed → torque/current loop
- Motor R/L auto-measurement
- Flux-linkage (Ke / λ) auto-detection
- FOC PI auto-tune
- Hall sensor alignment / sequence calibration
- Configurable limits (phase current, battery current, power, speed)

**Communication, configuration & infrastructure**

- Classic CAN (transceiver FD-capable), RS-485, USB, UART
- PC configuration tool over USB (tune gains, set bus voltage, run calibrations, save to flash)
- Structured fault dictionary + telemetry over CAN/USB
- Non-volatile parameter storage (flash, wear-aware, safe restore-defaults)
- Fault snapshot logging ("black box")
- Bootloader for field firmware update (USB/CAN) + SWD debug header
- HSE crystal (USB/CAN timing) + LSE crystal (RTC / timestamps)

---

## 1. System Overview

Vortex is powered by 24 V or 48 V batteries. Because the bus tracks battery state of charge,
the inverter sees 19–30 V (24 V pack) or 39–60 V (48 V pack). It drives any BLDC/PMSM motor
(500 W–5 kW) using FOC with SVPWM, commutated from Hall-effect sensors. The in-line current and
voltage of every phase are measured for control, monitoring, and protection.

Vortex is built from two PCBs:

- **Vector** — control board: MCU, voltage regulators, communication, and the sensing
  front-end. 4-layer stack (inner layers ground; top/bottom signal/power).
- **Flux** — power board / inverter: half-bridges, gate drivers, shunts, phase-voltage
  dividers, temperature sensors, bus capacitors, and the brake chopper. 2-layer, 4 oz copper,
  with the two layers stitched by vias (~8 oz equivalent where stitched).

The two boards connect via a 2.54 mm pin header (pinout in §9).

Because the driver accepts any 24 V or 48 V pack with no assumed chemistry or BMS, three input
requirements follow: reverse-polarity protection and pre-charge on the input (§5), and a regen
sink that does not rely on the battery accepting charge (§6).

---

## 2. Inverter / Power Stage (Flux)

Three half-bridges built from the **IPT015N10N5** N-channel MOSFET (100 V, ~1.5 mΩ, 300 A /
200 A at 100 °C case, ~169 nC gate charge). Two devices in parallel per switch → **4 FETs per
phase, 12 FETs total**. Each phase has one **UCC27211AQDDARQ1** half-bridge gate driver plus
passives. Gate signals come from the **STM32G473RCT6** advanced timer (TIM1) on Vector, over
the header.

**Gate drive**

- **Asymmetric gate resistors** with a split turn-on / turn-off path: a larger series turn-on
  resistor slows turn-on to limit dV/dt and reduce ringing/EMI and Miller-induced shoot-through;
  a smaller turn-off resistor through a parallel diode gives fast turn-off.
- **Individual gate resistors at each paralleled FET** to damp gate oscillation between the two
  devices, in addition to the shared turn-on/turn-off resistors at the driver.
- **Gate–source pulldown** on each FET so gates stay off before the driver is alive.
- **Dead-time** from the TIM1 complementary-output dead-time generator.
- **Bootstrap** high-side supply; maximum duty is limited slightly so that brief low-side
  conduction always refreshes the bootstrap capacitor.
- **Voltage margin:** the 100 V FET on a ≤70 V bus leaves headroom for switching overshoot; a
  tight commutation loop and decoupling (§3) keep overshoot inside that.

Passive component values (gate resistors, bootstrap, dead-time) are determined during detailed
design and validated on the bench (double-pulse / shoot-through test).

---

## 3. DC Bus & Decoupling

Switching frequency is 40 kHz; worst-case bus current is ~135 A (24 V pack at 19 V). Bus
capacitors and the brake chopper (§6) sit on Flux, close to the bridges.

- **Bulk:** a parallel bank of low-ESR polymer/electrolytic capacitors on the bus, rated above
  the maximum bus voltage and sized by ripple-current rating, with several in parallel sharing
  the ripple.
- **Decoupling:** ceramic capacitors immediately across each half-bridge (high + low FET pair),
  with the smallest possible commutation-loop area.
- **Commutation loop:** kept tight; switch-off overshoot is verified to stay under the 100 V FET
  rating.

Bulk-cap and decoupling values are determined during detailed design, against the measured
ripple current and commutation-loop overshoot.

---

## 4. Sensing — Current, Voltage & Temperature

**Phase current (Flux):** in-line sensing, 0.1 mΩ shunt (**ASR-K-7-1F**, 5930, 9 W) per phase →
**INA240** (gain 50). Common mode –4 V to +80 V suits the switching phase node; PWM rejection is
good to ~125 kHz (well above 40 kHz).

**Phase voltage (Flux):** divider 102 kΩ / 4.7 kΩ (÷22.7; 60 V → ~2.6 V) per phase. Used for
output monitoring, phase-loss / motor-disconnect detection, and diagnostics; it also leaves a
hardware path open for future sensorless operation without a board change.

**DC bus voltage:** a 100 kΩ / 4.7 kΩ divider (70 V → ~3.1 V) into the ADC. This is the
most-used analog channel in the drive — FOC modulation normalization, OVP/UVLO, brake-chopper
threshold, power calculation, and 24 V/48 V pack auto-detection at power-up.

**Board temperature (Flux):** three NTCs near the inverter, watching the power stage.

**Motor temperature:** a dedicated input for the motor's internal sensor. The reference motor
uses a **KTY84** silicon PTC (~603 Ω at 25 °C, ~1000 Ω at 100 °C, ~0.61 %/K, biased ~2 mA,
−40 to +300 °C). The front-end also accommodates NTC and PT1000 motor sensors.

**Front-end details**

- **INA240 powered from the analog 3.3 V rail** (TPS7A2033): midpoint 1.65 V, full scale
  **≈ ±330 A** at gain 50 — matched to the shunt and safe for the 3.3 V ADC.
- **Bidirectional reference:** REF1 → 3.3 V, REF2 → GND (1.65 V midpoint).
- **Kelvin (4-wire) sense** across each shunt's sense pads, routed as a tight differential pair.
- **Current-sense offset/gain auto-zero:** at power-up (gates off → zero current) all three
  INA240 channels are sampled to capture each channel's zero point, re-zeroed on disarm and
  tracked vs. temperature. Uncorrected offset shows up as torque ripple and DC injection.
- **Motor-temp front-end:** a pull-up (~2.2 kΩ) from analog 3.3 V to the sensor + ADC, with
  software linearization per sensor type, plus series + clamp protection on the cable line. A
  KTY84 gives ~0.46 V (−40 °C) to ~1.24 V (150 °C). Default trip ~120 °C motor.
- **Phase-voltage buffering:** the STM32G4 internal op-amps buffer the divider taps (the
  ~4.5 kΩ source impedance is too high to drive the ADC directly), with a light RC to attenuate
  switching.
- **NTC handling:** junction ≈ NTC + (P_loss × R_th(j→NTC)); thresholds warn 90 °C / derate
  100 °C / trip 110 °C board temp.
- **ADC plan:** the STM32G4 has 5 ADCs. A dual-ADC simultaneous injected conversion of the three
  phase currents is triggered by TIM1 (sampled at PWM center). Channels: 3 I + 3 phase V + V_bus
  + 3 board NTC + 1 motor temp ≈ 11.

---

## 5. Protection

- **Hardware fast-trip overcurrent:** a comparator (STM32G4 internal comparator, DAC-set
  threshold) routes the current sense into the **TIM1 BRK input** → PWM off in hardware, no MCU
  loop. Threshold ~220 A (above the ~175 A peak design point, below shunt/FET limits).
- **Overvoltage:** V_bus comparator trip ~68 V (just above the brake-chopper band, §6).
- **Undervoltage lockout:** stops switching below a pack-relative floor; absolute floor ~16 V so
  the 12 V gate rail stays in regulation.
- **Over-temperature:** board NTCs (§4) derate then shut down, plus the motor-temperature trip.
- **Gate-driver protection:** the UCC27211 has no desaturation/fault reporting, so the
  shunt-based OCP is the primary device protection.
- **Input fuse:** sized above the ~135 A continuous bus current for catastrophic protection only;
  electronic OCP handles fast events.
- **Reverse-polarity protection:** a low-R_ds ideal-diode (back-to-back / single N-FET in the
  return) rather than a series Schottky, given ~135 A. This FET can double as the pre-charge
  soft-start element.
- **Pre-charge / inrush limiting:** pre-charge resistor + bypass FET/contactor, sequenced by the
  MCU, charging the bus bank before the main path closes.
- **Phase-loss / motor-disconnect detection:** uses the per-phase current and voltage already
  sensed to flag an open phase or a disconnected motor, then disarms.
- **Overspeed / runaway detection:** an independent speed trip (distinct from stall) catching a
  sensor failure, then disarms.
- **ESD / surge protection on every external line:** TVS/clamp + series protection on all
  off-board interfaces — CAN, RS-485, USB (D+/D−, VBUS), UART, Hall sensors, and motor-temp.
  Because Vortex is non-isolated, this protection does the job isolation would otherwise do.
- **Short-circuit-to-rail on logic I/O:** clamp / series resistance on exposed digital I/O.

For reference, the 1.2 kW commercial controller trips at UVLO < 39 V, OVP > 58 V, overheat
85 °C, and a 25 A / 35 A (60 s) current limit — consistent with Vortex's pack-relative scheme,
which adds a regen sink instead of simply cutting out at the OVP point.

---

## 6. Regenerative Braking / Bus Overvoltage

When the motor decelerates or is back-driven it pushes energy into the bus. Since any pack can
be connected and may refuse charge, Vortex dissipates regen energy on-board.

- **Brake chopper:** a low-side MOSFET switching a power resistor across the DC bus, turned on
  when measured V_bus exceeds a firmware threshold set above the detected pack's full-charge
  voltage (e.g. ~33 V on a 24 V pack, ~63 V on a 48 V pack) so it never fires in normal use.
- **TVS / clamp** across the bus for fast transients the chopper loop cannot catch.
- **V_bus measurement** (§4) drives both the chopper and the §5 overvoltage trip.
- This sets the absolute-max-survive bus to ~70 V, keeping margin under the 100 V FETs, the 80 V
  INA240 common mode, and the 100 V LM5013 input.

The brake resistor (continuous power + pulse energy), the chopper FET, and the TVS clamp voltage
are sized from the application's worst-case deceleration profile.

---

## 7. Grounding & Layout Strategy

The system uses a **single, shared ground**: the power return, the analog/signal reference, and
all external interfaces sit on one common ground net. Noise immunity therefore comes from layout
rather than from ground partitioning:

- **Kelvin (4-wire) shunt sensing** so the high-current return cannot corrupt the current
  measurement.
- Route sensitive analog traces away from the high-di/dt switching-current return paths.
- Tie the sensing reference to the high-current ground close to the shunts' reference point, and
  use a solid, low-impedance ground pour to minimise shared-path voltage drops.

---

## 8. Thermal Management

The FETs mount to a custom water-cooled cold plate. Heat to remove at the ~125 A RMS design
point is ~65 W of conduction loss (≈ 3 × I_ph² × R_switch_hot) plus switching loss at 40 kHz and
shunt loss (~3 W/shunt at 175 A) — the cold plate is budgeted around ~100 W.

- Coolant design point: inlet temperature and flow rate (these govern junction temperature far
  more than air ambient).
- FET-tab-to-cold-plate interface: TIM, with electrical isolation if the plate is shared/grounded.
- Copper budget: trace-width / temperature-rise and IR-drop at ~175 A peak — the FET pads, shunt
  pads, and phase/battery terminals are the real bottlenecks, not the wide pours.
- LM5013 catch-diode dissipation (non-synchronous) — see §11.
- Phase / battery terminal connector current ratings.
- NTC-to-junction offset model (NTCs read the board, not the die) — see §4.

---

## 9. Inter-board Connector (Flux ↔ Vector)

The header carries: 6× PWM (HIN/LIN per phase), 12 V gate supply + return, 3× current-sense
analog + reference, 3× phase-voltage analog, V_bus sense, 3× board NTC, chopper control, enable,
fault, plus ground returns. Motor Hall/temperature signals arrive on the motor cable and land on
Vector directly — they do not cross this header.

- Interleave **ground pins** between the PWM lines and between the analog lines for return
  integrity.
- Give the **12 V gate-supply return generous, dedicated pin(s)** so its pulsed current does not
  share the sensing return path (even on a single ground net).
- Keep the **analog sense group** (currents, phase V, V_bus, NTC) on one contiguous region with a
  quiet ground reference, separated from the digital/PWM region.

The full pin-by-pin assignment, and whether the analog 3.3 V for the INA240s is generated on
Vector or on Flux, are fixed at layout.

---

## 10. Position Sensing

Commutation is sensored via **Hall-effect sensors**. The speed setpoint is commanded over the
communication interfaces (§12).

- **Hall-effect sensors:** 3 digital inputs with pull-ups (Hall outputs are open-collector), RC
  filtering, and ESD protection, into a timer. The reference 6-pin Hall connector wiring is
  Hall+ = red (5 V), Hall− = black (GND), and signals U/V/W = yellow/green/blue.
- **FOC angle from Halls:** the Hall sensors give six 60° sectors per electrical revolution; the
  continuous electrical angle FOC needs is obtained by interpolating between Hall transitions
  (a speed-based angle estimate / PLL), falling back to 60° sector resolution at very low speed
  and standstill.

A sensor connector provides 5 V + GND to the Hall sensors plus the three Hall signal lines.

The Hall sensor supply voltage and the angle-interpolation/observer tuning are finalized during
firmware bring-up.

---

## 11. Power Supply (Vector)

Four regulators / four rails:

- **LM5013DDAR** → 12 V at up to 3.5 A. Powers the gate drivers and the 5 V buck. Wide input
  (6–100 V), non-synchronous (external Schottky catch diode — account for its loss in §8).
- **TPS62913** (10–17 V in) → 5 V at up to 2.5 A. CAN transceiver + sensor supply.
- **TL1963ADCQR** LDO → main 3.3 V at up to 1.5 A (MCU / digital).
- **TPS7A2033PDQNR** LDO → 3.3 V analog for the sensing front-end (and the INA240s, §4).

- Rail budget is generous: gate drive averages <0.1 A on 12 V; 5 V is mostly the transceiver +
  sensors (~0.5 A); 3.3 V digital ~0.3 A; 3.3 V analog ~0.05 A.
- Sequencing: analog 3.3 V comes up before the MCU samples / sets the ADC reference.

---

## 12. Communication (Vector)

- **CAN:** the STM32G4 FDCAN peripheral with an FD-capable transceiver that has a 3.3 V VIO pin
  (e.g. MCP2562FD / TCAN1042V class) so logic levels match the 3.3 V MCU. Revision 1.0 runs
  classic CAN; the FD-capable transceiver leaves the faster mode available without a hardware
  change. Non-isolated.
- **RS-485 (ST485EDR):** DE/RE direction-control GPIO, switchable 120 Ω termination, fail-safe
  biasing, half-duplex. Logic-level matching between the 5 V transceiver and the 3.3 V MCU is
  handled at design (5 V-tolerant pin or a 3.3 V transceiver). Non-isolated.
- **USB (STM32G4 FS):** D+/D− ESD protection (TVS array) and a VBUS sense divider; the data-line
  pull-up is on-chip.
- **UART (STM32G4):** general-purpose serial.

The exact CAN transceiver, the RS-485 logic-level approach, and the comms connector pinout are
fixed during detailed design.

---

## 13. Clocking

- **HSE crystal** (e.g. 16 or 24 MHz): USB FS needs an accurate 48 MHz and CAN needs tight bit
  timing; the internal RC is not adequate for either.
- **LSE crystal** (32.768 kHz): drives the RTC for fault-snapshot timestamps (§16) and low-power
  timekeeping.

---

## 14. MCU Supervision & Hardware Safe-State

The communication watchdog (§5) catches a dead link; this section catches a hung or crashed MCU
that is still holding the bridge in a dangerous state. The goal is a fault path that does not
depend on firmware running.

- **Windowed watchdog:** STM32G4 WWDG, serviced from the control ISR, so both a hang and a
  runaway-fast loop trip it. An external watchdog/supervisor IC is an option for independence
  from the MCU clock.
- **Brown-out + supervisor:** on-chip BOR plus an external voltage supervisor on the 3.3 V rail
  force a clean reset below threshold.
- **Hardware gate-driver enable defaults OFF:** the gate-driver enable (and/or a series enable on
  the PWM path) is pulled to the disabled state, so on power-up, MCU reset, or brown-out the
  bridge stays off until firmware explicitly arms it.
- **TIM1 BRK fail-safe:** the OCP/OVP comparators (§5) and the watchdog/supervisor feed TIM1
  BRK/BRK2, which forces the PWM outputs to their inactive (safe) level in hardware, independent
  of code. A locked-up MCU still leaves the inverter safe.

---

## 15. Firmware / Control

**Control**

- **Inner current/torque loop:** FOC d/q PI on SVPWM.
- **Speed control:** the user sets a speed setpoint; an outer speed PI loop commands the
  torque/current reference, and the inner current loop regulates it — so the drive raises or
  lowers current/torque to hold the commanded speed as load changes. Accel/decel ramps are
  applied to the setpoint.
- **Position loop:** optional outer loop for servo use (future).
- **Field weakening:** optional, above base speed (future).

**Startup**

- Commutation is sensored, so the Hall sensors give the rotor's 60° sector at standstill. FOC
  starts from the known sector and refines the electrical angle by Hall interpolation as the
  motor turns; no open-loop ramp is required.

**Commissioning (run from the PC tool, §16)**

- Measure phase **resistance R** and **inductance L** (signal injection at standstill).
- Measure **flux linkage Ke / λ** (back-EMF constant) via the position sensor.
- **Auto-compute** the FOC current-loop and speed-loop PI gains from R / L / Ke.
- **Hall alignment / sequence calibration** (map the Hall pattern to the electrical angle and
  confirm the motor phase order).
- **Current-sense offset auto-zero** (gates off) — see §4.

**Configurable limits (stored in flash, §16)**

- Maximum phase current (RMS + peak), maximum battery/bus current, maximum power, max/min speed,
  accel/decel ramps, temperature derate points, and brake-chopper thresholds. The battery-current
  limit protects an arbitrary pack and is derived from the phase currents already measured.

**Fault state machine**

- States: init → precharge → self-test → standby/disarmed → armed/run → fault. Faults latch,
  force the hardware safe-state (§14 BRK), report over CAN/USB, snapshot to flash (§16), and
  recover per a defined policy.

The sensor offset/alignment routine and the speed-loop tuning targets are finalized during
firmware bring-up.

---

## 16. Configuration, Programming & Field Update

- **PC configuration tool (over USB):** tune the FOC and speed PI gains, set bus voltage / pack
  type, run R/L measurement and calibrations, set the configurable limits (§15), read live
  telemetry, and save to flash.
- **Non-volatile parameter storage:** motor parameters, calibration, limits, trip thresholds and
  pack configuration live in MCU flash via flash-emulated EEPROM with wear leveling and
  redundancy, a config version field, and a safe "restore defaults" path that cannot brick a
  partially written configuration.
- **Structured fault dictionary + telemetry:** enumerated fault codes with a documented
  dictionary, plus a live telemetry stream (phase currents, V_bus, temperatures, speed, state,
  flags) over CAN and USB.
- **Fault snapshot logging ("black box"):** on every trip, a snapshot — RTC timestamp (§13 LSE),
  V_bus, phase currents, temperatures, speed, state, and fault code — is stored to a flash ring
  buffer of the last N events for field diagnosis.
- **Bootloader for field firmware update:** image update over USB (DFU) and/or CAN, with image
  validation and rollback.
- **SWD debug header:** for bring-up and production programming.

The NV-storage scheme (emulated EEPROM vs external EEPROM/FRAM), the bootloader transport(s), and
the telemetry/command frame format are fixed during detailed design.

---

## Open Items / To Finalize

- [ ] FET thermal sign-off against the specific motor(s) the driver will ship with (their Kv /
      rated voltage / pole count)
- [ ] Operating ambient spec + coolant inlet temperature / flow rate (§0, §8)
- [ ] Bulk bus-cap bank value + parts, sized to measured ripple current (§3)
- [ ] Brake-resistor sizing from a worst-case braking profile; chopper FET + TVS clamp (§6)
- [ ] Gate-resistor values + dead-time, validated by double-pulse test (§2)
- [ ] Commutation-loop overshoot measurement (§3)
- [ ] Hall angle-interpolation / observer tuning and low-speed behaviour (§10, §15)
- [ ] Final inter-board connector pin assignment (§9)
- [ ] Exact CAN transceiver + RS-485 logic-level approach (§12)
- [ ] Internal WWDG only vs external watchdog/supervisor IC (§14)
- [ ] NV-storage scheme + bootloader transport (§16)
