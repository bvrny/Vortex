/* vx_protection.h — hardware protection threshold scaling with OVP backstop.
 *
 * Converts protection setpoints (amps, volts) into the DAC codes that feed
 * the OCP/OVP comparators (spec: INA240 gain-50 on 0.1 mOhm shunt -> 5 mV/A
 * centred on 1.65 V; vbus divider k = VP_VBUS_DIVIDER_K). The comparators +
 * TIM1 BRK act without firmware; these codes only position the thresholds.
 *
 * Backstop rule: threshold requests outside the protocol parameter bounds
 * (prot.overcurrent_a, prot.overvoltage_v) are REJECTED, never clamped —
 * a clamped protection limit silently differs from what the host asked for.
 */
#ifndef VX_PROTECTION_H
#define VX_PROTECTION_H

#include <stdbool.h>
#include <stdint.h>

#include "vortex_protocol.h"

#define VX_DAC_CODE_MAX 4095u

static inline uint16_t vx_dac_code_from_volts(float volts)
{
    float code = (volts / VP_VREF_V) * (float)VP_DAC_FULLSCALE + 0.5f;
    if (code < 0.0f) {
        return 0u;
    }
    if (code > (float)VX_DAC_CODE_MAX) {
        return VX_DAC_CODE_MAX;
    }
    return (uint16_t)code;
}

/* Comparator threshold for +amps phase current (upper trip). 150 A -> 2979. */
static inline uint16_t vx_ocp_dac_code_high(float amps)
{
    return vx_dac_code_from_volts(VP_INA240_VREF_V + amps * VP_CURRENT_SENSE_V_PER_A);
}

/* Comparator threshold for -amps phase current (lower trip). */
static inline uint16_t vx_ocp_dac_code_low(float amps)
{
    return vx_dac_code_from_volts(VP_INA240_VREF_V - amps * VP_CURRENT_SENSE_V_PER_A);
}

/* Comparator threshold for a bus voltage in volts (after divider). */
static inline uint16_t vx_ovp_dac_code(float vbus_v)
{
    return vx_dac_code_from_volts(vbus_v * VP_VBUS_DIVIDER_K);
}

static inline const vp_param_meta_t *vx_prot_meta(uint16_t id)
{
    uint32_t i;
    for (i = 0u; i < VP_PARAM_COUNT; i++) {
        if (VP_PARAMS[i].id == id) {
            return &VP_PARAMS[i];
        }
    }
    return NULL;
}

/* Validate + convert an overcurrent setpoint. false = rejected (no output). */
static inline bool vx_ocp_codes(float amps, uint16_t *code_high, uint16_t *code_low)
{
    const vp_param_meta_t *m = vx_prot_meta(0x0201u); /* prot.overcurrent_a */
    if ((m == NULL) || (amps < m->min) || (amps > m->max)) {
        return false;
    }
    *code_high = vx_ocp_dac_code_high(amps);
    *code_low = vx_ocp_dac_code_low(amps);
    return true;
}

/* Validate + convert an overvoltage setpoint. Bounds (63.5..65.5 V) keep the
 * threshold above the 63 V brake target and below the ~66 V hardware
 * backstop. false = rejected. */
static inline bool vx_ovp_code(float volts, uint16_t *code)
{
    const vp_param_meta_t *m = vx_prot_meta(0x0202u); /* prot.overvoltage_v */
    if ((m == NULL) || (volts < m->min) || (volts > m->max)) {
        return false;
    }
    *code = vx_ovp_dac_code(volts);
    return true;
}

#endif /* VX_PROTECTION_H */
