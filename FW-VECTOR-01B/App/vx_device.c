#include "vx_device.h"

#include <string.h>

#include "vx_protection.h"

#define PARAM_ID_R_PHASE 0x0002u
#define PARAM_ID_L_D 0x0003u
#define PARAM_ID_L_Q 0x0004u
#define PARAM_ID_FLUX 0x0005u
#define PARAM_ID_OVERCURRENT 0x0201u
#define PARAM_ID_OVERVOLTAGE 0x0202u

#define SCOPE_READ_MAX_CHUNK (VP_MAX_PAYLOAD - 9u) /* status + total + offset */

/* ------------------------------------------------------------ helpers */

static void put_u16(uint8_t *dst, uint16_t v)
{
    dst[0] = (uint8_t)(v & 0xFFu);
    dst[1] = (uint8_t)(v >> 8);
}

static void put_u32(uint8_t *dst, uint32_t v)
{
    dst[0] = (uint8_t)(v & 0xFFu);
    dst[1] = (uint8_t)((v >> 8) & 0xFFu);
    dst[2] = (uint8_t)((v >> 16) & 0xFFu);
    dst[3] = (uint8_t)((v >> 24) & 0xFFu);
}

static uint16_t get_u16(const uint8_t *src)
{
    return (uint16_t)((uint16_t)src[0] | ((uint16_t)src[1] << 8));
}

static uint32_t get_u32(const uint8_t *src)
{
    return (uint32_t)src[0] | ((uint32_t)src[1] << 8) |
           ((uint32_t)src[2] << 16) | ((uint32_t)src[3] << 24);
}

static float get_f32(const uint8_t *src)
{
    float f;
    uint32_t u = get_u32(src);
    (void)memcpy(&f, &u, 4u);
    return f;
}

static bool is_energized(const vx_device_t *d)
{
    return (d->state == VP_DEVICE_STATE_ARMED) ||
           (d->state == VP_DEVICE_STATE_RUNNING);
}

/* PWM off + setpoint zeroed + latch; transient conditions (heartbeat loss)
 * latch without staying active. */
static void trip(vx_device_t *d, uint8_t bit, bool transient)
{
    d->fault_latched |= (1uL << bit);
    if (!transient) {
        d->fault_active |= (1uL << bit);
    }
    d->setpoint = 0.0f;
    d->state = VP_DEVICE_STATE_FAULT;
    vx_hb_stop(&d->hb);
}

static void update_protection_codes(vx_device_t *d)
{
    float oc = 0.0f;
    float ov = 0.0f;
    (void)vx_param_read(&d->params, PARAM_ID_OVERCURRENT, &oc);
    (void)vx_param_read(&d->params, PARAM_ID_OVERVOLTAGE, &ov);
    (void)vx_ocp_codes(oc, &d->ocp_code_high, &d->ocp_code_low);
    (void)vx_ovp_code(ov, &d->ovp_code);
}

/* Response: status byte + (extra only when OK), per PROTOCOL.md §2. */
static int32_t reply(const vp_frame_t *f, vp_status_t status,
                     const uint8_t *extra, uint16_t extra_len,
                     uint8_t *out, uint16_t cap)
{
    uint8_t payload[VP_MAX_PAYLOAD];
    uint16_t len = 1u;

    payload[0] = (uint8_t)status;
    if ((status == VP_STATUS_OK) && (extra_len > 0u)) {
        (void)memcpy(&payload[1], extra, extra_len);
        len = (uint16_t)(1u + extra_len);
    }
    return vp_encode_wire(out, cap, f->cmd, f->seq, VP_FLAG_RESPONSE,
                          payload, len);
}

/* ------------------------------------------------------------ lifecycle */

void vx_device_init(vx_device_t *d, const vx_nv_ops_t *nv)
{
    (void)memset(d, 0, sizeof *d);
    d->nv = nv;
    d->state = VP_DEVICE_STATE_INIT;
    vx_params_defaults(&d->params);
    vx_hb_init(&d->hb);
    d->telem_decimation = 8u;
    if (nv != NULL) {
        uint8_t blob[VX_PARAM_NV_MAX_SIZE];
        int32_t n = vx_nv_load(nv, blob, sizeof blob);
        if (n > 0) {
            (void)vx_params_nv_deserialize(&d->params, blob, (size_t)n);
        }
    }
    update_protection_codes(d);
}

void vx_device_ready(vx_device_t *d)
{
    if (d->state == VP_DEVICE_STATE_INIT) {
        d->state = VP_DEVICE_STATE_STANDBY;
    }
}

void vx_device_fault_set(vx_device_t *d, uint8_t bit)
{
    trip(d, bit, false);
}

void vx_device_fault_clear_condition(vx_device_t *d, uint8_t bit)
{
    d->fault_active &= ~(1uL << bit);
}

void vx_device_tick(vx_device_t *d, uint32_t now_ms)
{
    if (is_energized(d) && vx_hb_expired(&d->hb, now_ms)) {
        trip(d, VP_FAULT_HEARTBEAT_LOSS_BIT, true);
    }
}

void vx_device_motor_id_finish(vx_device_t *d, float r, float l_d, float l_q,
                               float flux)
{
    (void)vx_param_write(&d->params, PARAM_ID_R_PHASE, r);
    (void)vx_param_write(&d->params, PARAM_ID_L_D, l_d);
    (void)vx_param_write(&d->params, PARAM_ID_L_Q, l_q);
    (void)vx_param_write(&d->params, PARAM_ID_FLUX, flux);
    d->motor_id_active = false;
}

void vx_device_motor_id_fail(vx_device_t *d)
{
    d->motor_id_active = false;
}

int32_t vx_device_emit(vx_device_t *d, uint8_t cmd, const uint8_t *payload,
                       uint16_t len, uint8_t *out, uint16_t cap)
{
    d->tx_seq++;
    return vp_encode_wire(out, cap, cmd, d->tx_seq, 0u, payload, len);
}

void vx_device_set_scope_capture(vx_device_t *d, const uint8_t *data,
                                 uint32_t len)
{
    d->scope_capture = data;
    d->scope_capture_len = len;
    d->scope_trigger_requested = false;
}

/* ------------------------------------------------------------ commands */

static int32_t cmd_hello(const vp_frame_t *f, uint8_t *out, uint16_t cap)
{
    uint8_t extra[2] = { VP_PROTOCOL_VERSION_MAJOR, VP_PROTOCOL_VERSION_MINOR };
    return reply(f, VP_STATUS_OK, extra, sizeof extra, out, cap);
}

static int32_t cmd_device_info(vx_device_t *d, const vp_frame_t *f,
                               uint8_t *out, uint16_t cap)
{
    uint8_t extra[3u + VX_UID_LEN + sizeof VX_DEVICE_NAME - 1u];
    extra[0] = VX_FW_VERSION_MAJOR;
    extra[1] = VX_FW_VERSION_MINOR;
    extra[2] = VX_FW_VERSION_PATCH;
    (void)memcpy(&extra[3], d->uid, VX_UID_LEN);
    (void)memcpy(&extra[3u + VX_UID_LEN], VX_DEVICE_NAME,
                 sizeof VX_DEVICE_NAME - 1u);
    return reply(f, VP_STATUS_OK, extra, (uint16_t)sizeof extra, out, cap);
}

static int32_t cmd_param_list(const vp_frame_t *f, uint8_t *out, uint16_t cap)
{
    uint8_t extra[2u + (VP_PARAM_COUNT * 2u)];
    uint32_t i;
    put_u16(&extra[0], (uint16_t)VP_PARAM_COUNT);
    for (i = 0u; i < VP_PARAM_COUNT; i++) {
        put_u16(&extra[2u + (i * 2u)], VP_PARAMS[i].id);
    }
    return reply(f, VP_STATUS_OK, extra, (uint16_t)sizeof extra, out, cap);
}

static int32_t cmd_param_read(vx_device_t *d, const vp_frame_t *f,
                              uint8_t *out, uint16_t cap)
{
    uint8_t extra[6];
    uint16_t id;
    int32_t idx;
    uint8_t vsize;

    if (f->len != 2u) {
        return reply(f, VP_STATUS_NACK_BAD_LEN, NULL, 0u, out, cap);
    }
    id = get_u16(f->payload);
    idx = vx_param_index(id);
    if (idx < 0) {
        return reply(f, VP_STATUS_NACK_BAD_PARAM, NULL, 0u, out, cap);
    }
    put_u16(&extra[0], id);
    vsize = vx_param_encode_value(&VP_PARAMS[idx], d->params.values[idx],
                                  &extra[2]);
    return reply(f, VP_STATUS_OK, extra, (uint16_t)(2u + vsize), out, cap);
}

static int32_t cmd_param_write(vx_device_t *d, const vp_frame_t *f,
                               uint8_t *out, uint16_t cap)
{
    uint16_t id;
    int32_t idx;
    float value;
    vp_status_t status;
    uint8_t extra[2];

    if (f->len < 2u) {
        return reply(f, VP_STATUS_NACK_BAD_LEN, NULL, 0u, out, cap);
    }
    id = get_u16(f->payload);
    idx = vx_param_index(id);
    if ((idx < 0) || (VP_PARAMS[idx].is_rw == 0u)) {
        return reply(f, VP_STATUS_NACK_BAD_PARAM, NULL, 0u, out, cap);
    }
    if (is_energized(d)) {
        return reply(f, VP_STATUS_NACK_BAD_STATE, NULL, 0u, out, cap);
    }
    if (!vx_param_decode_value(&VP_PARAMS[idx], &f->payload[2],
                               (uint16_t)(f->len - 2u), &value)) {
        return reply(f, VP_STATUS_NACK_BAD_LEN, NULL, 0u, out, cap);
    }
    status = vx_param_write(&d->params, id, value);
    if (status != VP_STATUS_OK) {
        return reply(f, status, NULL, 0u, out, cap);
    }
    if ((id == PARAM_ID_OVERCURRENT) || (id == PARAM_ID_OVERVOLTAGE)) {
        update_protection_codes(d);
    }
    put_u16(extra, id);
    return reply(f, VP_STATUS_OK, extra, 2u, out, cap);
}

static int32_t cmd_param_save(vx_device_t *d, const vp_frame_t *f,
                              uint8_t *out, uint16_t cap)
{
    uint8_t blob[VX_PARAM_NV_MAX_SIZE];
    size_t n;

    if (d->nv == NULL) {
        return reply(f, VP_STATUS_NACK_BAD_STATE, NULL, 0u, out, cap);
    }
    n = vx_params_nv_serialize(&d->params, blob, sizeof blob);
    if ((n == 0u) || !vx_nv_save(d->nv, blob, (uint16_t)n)) {
        return reply(f, VP_STATUS_NACK_BAD_STATE, NULL, 0u, out, cap);
    }
    return reply(f, VP_STATUS_OK, NULL, 0u, out, cap);
}

static int32_t cmd_param_load(vx_device_t *d, const vp_frame_t *f,
                              uint8_t *out, uint16_t cap)
{
    uint8_t blob[VX_PARAM_NV_MAX_SIZE];
    int32_t n;

    if (d->nv == NULL) {
        return reply(f, VP_STATUS_NACK_BAD_STATE, NULL, 0u, out, cap);
    }
    n = vx_nv_load(d->nv, blob, sizeof blob);
    if ((n <= 0) || !vx_params_nv_deserialize(&d->params, blob, (size_t)n)) {
        return reply(f, VP_STATUS_NACK_BAD_STATE, NULL, 0u, out, cap);
    }
    update_protection_codes(d);
    return reply(f, VP_STATUS_OK, NULL, 0u, out, cap);
}

static int32_t cmd_param_default(vx_device_t *d, const vp_frame_t *f,
                                 uint8_t *out, uint16_t cap)
{
    if (is_energized(d)) {
        return reply(f, VP_STATUS_NACK_BAD_STATE, NULL, 0u, out, cap);
    }
    vx_params_defaults(&d->params);
    update_protection_codes(d);
    return reply(f, VP_STATUS_OK, NULL, 0u, out, cap);
}

static int32_t cmd_telemetry_start(vx_device_t *d, const vp_frame_t *f,
                                   uint8_t *out, uint16_t cap)
{
    uint32_t mask;
    uint16_t dec;

    if (f->len != 6u) {
        return reply(f, VP_STATUS_NACK_BAD_LEN, NULL, 0u, out, cap);
    }
    mask = get_u32(&f->payload[0]);
    dec = get_u16(&f->payload[4]);
    if ((mask == 0u) || (dec < 1u)) {
        return reply(f, VP_STATUS_NACK_OUT_OF_BOUNDS, NULL, 0u, out, cap);
    }
    d->telem_mask = mask;
    d->telem_decimation = dec;
    d->telem_on = true;
    return reply(f, VP_STATUS_OK, NULL, 0u, out, cap);
}

static int32_t cmd_motor_id_start(vx_device_t *d, const vp_frame_t *f,
                                  uint8_t *out, uint16_t cap)
{
    if (d->motor_id_active) {
        return reply(f, VP_STATUS_BUSY, NULL, 0u, out, cap);
    }
    if (d->state != VP_DEVICE_STATE_STANDBY) {
        return reply(f, VP_STATUS_NACK_BAD_STATE, NULL, 0u, out, cap);
    }
    d->motor_id_active = true;
    return reply(f, VP_STATUS_OK, NULL, 0u, out, cap);
}

static int32_t cmd_protection_set(vx_device_t *d, const vp_frame_t *f,
                                  uint8_t *out, uint16_t cap)
{
    float oc;
    float ov;

    if (f->len != 8u) {
        return reply(f, VP_STATUS_NACK_BAD_LEN, NULL, 0u, out, cap);
    }
    oc = get_f32(&f->payload[0]);
    ov = get_f32(&f->payload[4]);
    /* Reject BOTH before applying either: thresholds change atomically. */
    if (!vx_ocp_codes(oc, &d->ocp_code_high, &d->ocp_code_low) ||
        !vx_ovp_code(ov, &d->ovp_code)) {
        update_protection_codes(d); /* restore codes from current params */
        return reply(f, VP_STATUS_NACK_OUT_OF_BOUNDS, NULL, 0u, out, cap);
    }
    (void)vx_param_write(&d->params, PARAM_ID_OVERCURRENT, oc);
    (void)vx_param_write(&d->params, PARAM_ID_OVERVOLTAGE, ov);
    return reply(f, VP_STATUS_OK, NULL, 0u, out, cap);
}

static int32_t cmd_fault_read(vx_device_t *d, const vp_frame_t *f,
                              uint8_t *out, uint16_t cap)
{
    uint8_t extra[8];
    put_u32(&extra[0], d->fault_active);
    put_u32(&extra[4], d->fault_latched);
    return reply(f, VP_STATUS_OK, extra, sizeof extra, out, cap);
}

static int32_t cmd_fault_clear(vx_device_t *d, const vp_frame_t *f,
                               uint8_t *out, uint16_t cap)
{
    if (d->fault_active != 0u) {
        return reply(f, VP_STATUS_NACK_BAD_STATE, NULL, 0u, out, cap);
    }
    d->fault_latched = 0u;
    if (d->state == VP_DEVICE_STATE_FAULT) {
        d->state = VP_DEVICE_STATE_STANDBY;
    }
    return reply(f, VP_STATUS_OK, NULL, 0u, out, cap);
}

static int32_t cmd_arm(vx_device_t *d, const vp_frame_t *f, uint32_t now_ms,
                       uint8_t *out, uint16_t cap)
{
    if (d->motor_id_active) {
        return reply(f, VP_STATUS_BUSY, NULL, 0u, out, cap);
    }
    if (d->state != VP_DEVICE_STATE_STANDBY) {
        return reply(f, VP_STATUS_NACK_BAD_STATE, NULL, 0u, out, cap);
    }
    d->state = VP_DEVICE_STATE_ARMED;
    vx_hb_start(&d->hb, now_ms);
    return reply(f, VP_STATUS_OK, NULL, 0u, out, cap);
}

static int32_t cmd_disarm_or_stop(vx_device_t *d, const vp_frame_t *f,
                                  uint8_t *out, uint16_t cap)
{
    /* STOP semantics == DISARM at this layer and always honored:
     * zero setpoint, PWM off; FAULT stays FAULT. */
    d->setpoint = 0.0f;
    if (is_energized(d)) {
        d->state = VP_DEVICE_STATE_STANDBY;
    }
    vx_hb_stop(&d->hb);
    return reply(f, VP_STATUS_OK, NULL, 0u, out, cap);
}

static int32_t cmd_setpoint(vx_device_t *d, const vp_frame_t *f,
                            uint8_t *out, uint16_t cap)
{
    uint8_t mode;
    float value;

    if (f->len != 5u) {
        return reply(f, VP_STATUS_NACK_BAD_LEN, NULL, 0u, out, cap);
    }
    mode = f->payload[0];
    value = get_f32(&f->payload[1]);
    if ((mode != (uint8_t)VP_SETPOINT_MODE_TORQUE) &&
        (mode != (uint8_t)VP_SETPOINT_MODE_SPEED)) {
        return reply(f, VP_STATUS_NACK_BAD_PARAM, NULL, 0u, out, cap);
    }
    if (!is_energized(d)) {
        return reply(f, VP_STATUS_NACK_BAD_STATE, NULL, 0u, out, cap);
    }
    d->setpoint_mode = mode;
    d->setpoint = value;
    d->state = (value != 0.0f) ? VP_DEVICE_STATE_RUNNING
                               : VP_DEVICE_STATE_ARMED;
    return reply(f, VP_STATUS_OK, NULL, 0u, out, cap);
}

static int32_t cmd_scope_config(vx_device_t *d, const vp_frame_t *f,
                                uint8_t *out, uint16_t cap)
{
    uint32_t mask;
    uint16_t dec;

    if (f->len != 12u) {
        return reply(f, VP_STATUS_NACK_BAD_LEN, NULL, 0u, out, cap);
    }
    mask = get_u32(&f->payload[0]);
    dec = get_u16(&f->payload[4]);
    if ((mask == 0u) || (dec < 1u)) {
        return reply(f, VP_STATUS_NACK_OUT_OF_BOUNDS, NULL, 0u, out, cap);
    }
    d->scope.mask = mask;
    d->scope.decimation = dec;
    d->scope.pretrigger = get_u16(&f->payload[6]);
    d->scope.trig_channel = f->payload[8];
    d->scope.trig_edge = f->payload[9];
    d->scope.trig_level = (int16_t)get_u16(&f->payload[10]);
    d->scope.configured = true;
    return reply(f, VP_STATUS_OK, NULL, 0u, out, cap);
}

static int32_t cmd_scope_arm(vx_device_t *d, const vp_frame_t *f,
                             uint8_t *out, uint16_t cap)
{
    if (!d->scope.configured) {
        return reply(f, VP_STATUS_NACK_BAD_STATE, NULL, 0u, out, cap);
    }
    d->scope_trigger_requested = true;
    return reply(f, VP_STATUS_OK, NULL, 0u, out, cap);
}

static int32_t cmd_scope_read(vx_device_t *d, const vp_frame_t *f,
                              uint8_t *out, uint16_t cap)
{
    uint8_t extra[8u + SCOPE_READ_MAX_CHUNK];
    uint32_t offset;
    uint32_t chunk;

    if (d->scope_capture == NULL) {
        return reply(f, VP_STATUS_NACK_BAD_STATE, NULL, 0u, out, cap);
    }
    if (f->len != 4u) {
        return reply(f, VP_STATUS_NACK_BAD_LEN, NULL, 0u, out, cap);
    }
    offset = get_u32(f->payload);
    if (offset > d->scope_capture_len) {
        return reply(f, VP_STATUS_NACK_OUT_OF_BOUNDS, NULL, 0u, out, cap);
    }
    chunk = d->scope_capture_len - offset;
    if (chunk > SCOPE_READ_MAX_CHUNK) {
        chunk = SCOPE_READ_MAX_CHUNK;
    }
    put_u32(&extra[0], d->scope_capture_len);
    put_u32(&extra[4], offset);
    (void)memcpy(&extra[8], &d->scope_capture[offset], chunk);
    return reply(f, VP_STATUS_OK, extra, (uint16_t)(8u + chunk), out, cap);
}

static int32_t cmd_heartbeat(vx_device_t *d, const vp_frame_t *f,
                             uint32_t now_ms, uint8_t *out, uint16_t cap)
{
    uint8_t extra[5];
    vx_hb_feed(&d->hb, now_ms);
    extra[0] = (uint8_t)d->state;
    put_u32(&extra[1], d->fault_active);
    return reply(f, VP_STATUS_OK, extra, sizeof extra, out, cap);
}

/* ------------------------------------------------------------ dispatch */

int32_t vx_device_handle_frame(vx_device_t *d, const vp_frame_t *f,
                               uint32_t now_ms, uint8_t *out, uint16_t cap)
{
    if (f->ver != VP_PROTOCOL_VERSION_MAJOR) {
        d->dropped_ver++;
        return 0;
    }
    switch (f->cmd) {
    case VP_CMD_HELLO:
        return cmd_hello(f, out, cap);
    case VP_CMD_DEVICE_INFO:
        return cmd_device_info(d, f, out, cap);
    case VP_CMD_PARAM_LIST:
        return cmd_param_list(f, out, cap);
    case VP_CMD_PARAM_READ:
        return cmd_param_read(d, f, out, cap);
    case VP_CMD_PARAM_WRITE:
        return cmd_param_write(d, f, out, cap);
    case VP_CMD_PARAM_SAVE:
        return cmd_param_save(d, f, out, cap);
    case VP_CMD_PARAM_LOAD:
        return cmd_param_load(d, f, out, cap);
    case VP_CMD_PARAM_DEFAULT:
        return cmd_param_default(d, f, out, cap);
    case VP_CMD_TELEMETRY_START:
        return cmd_telemetry_start(d, f, out, cap);
    case VP_CMD_TELEMETRY_STOP:
        d->telem_on = false;
        return reply(f, VP_STATUS_OK, NULL, 0u, out, cap);
    case VP_CMD_MOTOR_ID_START:
        return cmd_motor_id_start(d, f, out, cap);
    case VP_CMD_MOTOR_ID_ABORT:
        d->motor_id_active = false;
        return reply(f, VP_STATUS_OK, NULL, 0u, out, cap);
    case VP_CMD_PROTECTION_SET:
        return cmd_protection_set(d, f, out, cap);
    case VP_CMD_FAULT_READ:
        return cmd_fault_read(d, f, out, cap);
    case VP_CMD_FAULT_CLEAR:
        return cmd_fault_clear(d, f, out, cap);
    case VP_CMD_ARM:
        return cmd_arm(d, f, now_ms, out, cap);
    case VP_CMD_DISARM:
    case VP_CMD_STOP:
        return cmd_disarm_or_stop(d, f, out, cap);
    case VP_CMD_SETPOINT:
        return cmd_setpoint(d, f, out, cap);
    case VP_CMD_SCOPE_CONFIG:
        return cmd_scope_config(d, f, out, cap);
    case VP_CMD_SCOPE_ARM:
        return cmd_scope_arm(d, f, out, cap);
    case VP_CMD_SCOPE_READ:
        return cmd_scope_read(d, f, out, cap);
    case VP_CMD_REBOOT:
        d->pending = VX_ACTION_REBOOT;
        return reply(f, VP_STATUS_OK, NULL, 0u, out, cap);
    case VP_CMD_ENTER_DFU:
        d->pending = VX_ACTION_ENTER_DFU;
        return reply(f, VP_STATUS_OK, NULL, 0u, out, cap);
    case VP_CMD_HEARTBEAT:
        return cmd_heartbeat(d, f, now_ms, out, cap);
    default:
        return reply(f, VP_STATUS_NACK_UNKNOWN_CMD, NULL, 0u, out, cap);
    }
}
