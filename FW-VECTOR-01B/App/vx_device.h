/* vx_device.h — protocol command handler + device state machine.
 *
 * Behavior contract: PROTOCOL.md §2/§3/§5, reference implementation
 * APP-VORTEX/simulator/device.py (SimDevice). Runs in the main loop, never
 * in the control ISR. Hardware effects (PWM enable, DAC thresholds, actual
 * reboot/DFU jump, motor-ID sequencing, telemetry sampling) belong to the
 * target glue, which reads the flags/getters this module maintains.
 */
#ifndef VX_DEVICE_H
#define VX_DEVICE_H

#include <stdbool.h>
#include <stdint.h>

#include "vortex_protocol.h"
#include "vx_heartbeat.h"
#include "vx_nv_store.h"
#include "vx_param_store.h"

#define VX_FW_VERSION_MAJOR 0u
#define VX_FW_VERSION_MINOR 1u
#define VX_FW_VERSION_PATCH 0u
#define VX_DEVICE_NAME "Vortex"
#define VX_UID_LEN 12u

typedef enum {
    VX_ACTION_NONE = 0,
    VX_ACTION_REBOOT,
    VX_ACTION_ENTER_DFU,
} vx_pending_action_t;

typedef struct {
    uint32_t mask;
    uint16_t decimation;
    uint16_t pretrigger;
    uint8_t trig_channel;
    uint8_t trig_edge;
    int16_t trig_level;
    bool configured;
} vx_scope_cfg_t;

typedef struct {
    vx_params_t params;
    vp_device_state_t state;
    uint32_t fault_active;
    uint32_t fault_latched;
    vx_heartbeat_t hb;

    bool telem_on;
    uint32_t telem_mask;
    uint16_t telem_decimation;

    uint8_t setpoint_mode; /* vp_setpoint_mode_t */
    float setpoint;

    bool motor_id_active;

    vx_scope_cfg_t scope;
    bool scope_trigger_requested;   /* set by SCOPE_ARM, cleared by glue */
    const uint8_t *scope_capture;   /* installed by glue when capture done */
    uint32_t scope_capture_len;

    /* Updated by PROTECTION_SET (also set from params at init). */
    uint16_t ocp_code_high;
    uint16_t ocp_code_low;
    uint16_t ovp_code;

    const vx_nv_ops_t *nv;          /* NULL = no NV backend */
    uint8_t uid[VX_UID_LEN];        /* target fills from UID registers */
    vx_pending_action_t pending;    /* glue executes + clears */

    uint8_t tx_seq;                 /* unsolicited stream sequence */
    uint16_t dropped_ver;           /* frames dropped for wrong VER */
} vx_device_t;

/* Starts in INIT with defaults loaded, then NV params applied if present. */
void vx_device_init(vx_device_t *d, const vx_nv_ops_t *nv);

/* Target glue calls this once precharge + self-test pass: INIT -> STANDBY. */
void vx_device_ready(vx_device_t *d);

/* Hardware fault condition asserted / deasserted (comparators, sensors). */
void vx_device_fault_set(vx_device_t *d, uint8_t bit);
void vx_device_fault_clear_condition(vx_device_t *d, uint8_t bit);

/* Periodic housekeeping (heartbeat watchdog). Call from the main loop. */
void vx_device_tick(vx_device_t *d, uint32_t now_ms);

/* Handle one decoded frame; writes the wire response into out.
 * Returns wire length, 0 = no response (wrong VER). */
int32_t vx_device_handle_frame(vx_device_t *d, const vp_frame_t *f,
                               uint32_t now_ms, uint8_t *out, uint16_t cap);

/* Motor identification: the control task finishes or fails the sequence
 * started by MOTOR_ID_START. finish writes the results into the params. */
void vx_device_motor_id_finish(vx_device_t *d, float r, float l_d, float l_q,
                               float flux);
void vx_device_motor_id_fail(vx_device_t *d);

/* Build an unsolicited device->host frame (TELEMETRY_DATA /
 * MOTOR_ID_PROGRESS payloads). Returns wire length or -1. */
int32_t vx_device_emit(vx_device_t *d, uint8_t cmd, const uint8_t *payload,
                       uint16_t len, uint8_t *out, uint16_t cap);

/* Glue installs a finished scope capture (telemetry-batch format). */
void vx_device_set_scope_capture(vx_device_t *d, const uint8_t *data,
                                 uint32_t len);

#endif /* VX_DEVICE_H */
