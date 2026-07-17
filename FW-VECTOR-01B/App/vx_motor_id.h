/* vx_motor_id.h — motor identification math and current-loop gain design.
 *
 * Pure functions; the measurement sequencing (DC injection, step response,
 * spin-down) lives in the control task on target. Spec (VortexExplanation
 * §motor-id): R from DC V/I, L from the R-L step time constant, flux from
 * back-EMF at known electrical speed. Gains: Kp = L*w_bw, Ki = R*w_bw
 * (series PI, w_bw in rad/s) — matches the iloop.kp/ki defaults in
 * protocol.yaml (R=0.02, L=2e-5, 2666.667 Hz -> Kp=0.3351, Ki=335.1).
 */
#ifndef VX_MOTOR_ID_H
#define VX_MOTOR_ID_H

#include <stdbool.h>

#define VX_TWO_PI 6.283185307179586f

/* Phase resistance from steady-state DC injection. false if i is ~0. */
static inline bool vx_id_resistance(float v_dc, float i_dc, float *r_ohm)
{
    if ((i_dc < 1e-3f) && (i_dc > -1e-3f)) {
        return false;
    }
    *r_ohm = v_dc / i_dc;
    return true;
}

/* Inductance from the measured R-L rise time constant tau = L/R. */
static inline bool vx_id_inductance(float tau_s, float r_ohm, float *l_h)
{
    if ((tau_s <= 0.0f) || (r_ohm <= 0.0f)) {
        return false;
    }
    *l_h = tau_s * r_ohm;
    return true;
}

/* Flux linkage from phase back-EMF peak at electrical speed w_e (rad/s):
 * lambda = E_peak / w_e. */
static inline bool vx_id_flux(float bemf_peak_v, float w_e_rad_s, float *flux_wb)
{
    if (w_e_rad_s <= 1e-3f) {
        return false;
    }
    *flux_wb = bemf_peak_v / w_e_rad_s;
    return true;
}

/* Current-loop PI gains for a first-order target bandwidth. */
static inline void vx_iloop_gains(float r_ohm, float l_h, float bandwidth_hz,
                                  float *kp, float *ki)
{
    float w_bw = VX_TWO_PI * bandwidth_hz;
    *kp = l_h * w_bw;
    *ki = r_ohm * w_bw;
}

#endif /* VX_MOTOR_ID_H */
