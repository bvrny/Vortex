/*
 * =============================================================
 * GENERATED FILE — DO NOT EDIT.
 * Source of truth: PROTO-VORTEX-01A/protocol.yaml
 * Regenerate with: python PROTO-VORTEX-01A/codegen/generate.py
 * protocol.yaml sha256: aaf60cde46dfceebb75eb0dc2986f788d1cfde5ad1aee46c5aef5c282c750c12
 * =============================================================
 */
#ifndef VORTEX_PROTOCOL_H
#define VORTEX_PROTOCOL_H

#include <stdint.h>
#include <stddef.h>
#include <string.h>

/* NOTE: header-only by design so firmware and host tests share one
 * artifact. Tables and functions are static; include from the few
 * translation units that need them. */

#define VP_PROTOCOL_VERSION_MAJOR 1u
#define VP_PROTOCOL_VERSION_MINOR 0u
#define VP_SYNC 0xA5u
#define VP_MAX_PAYLOAD 512u
#define VP_FLAG_RESPONSE 0x01u
#define VP_USB_VID 0x0483u
#define VP_USB_PID 0x5740u
/* SAFETY-CRITICAL: link watchdog window while ARMED/RUNNING */
#define VP_HEARTBEAT_TIMEOUT_MS 200u
#define VP_HEARTBEAT_PERIOD_MS 50u

/* Hardware constants (see protocol.yaml + design spec) */
#define VP_FSW_HZ 40000u
#define VP_VREF_V 3.3f
#define VP_DAC_FULLSCALE 4096u
#define VP_CURRENT_SENSE_V_PER_A 0.005f
#define VP_INA240_VREF_V 1.65f
#define VP_VBUS_DIVIDER_K 0.0448901623686723f
#define VP_VBUS_OPERATING_MAX_V 60.0f
#define VP_VBUS_SURVIVE_MAX_V 70.0f
#define VP_BRAKE_TARGET_V 63.0f
#define VP_BRAKE_BACKSTOP_V 66.0f

typedef enum {
    VP_CMD_HELLO = 0x01,
    VP_CMD_DEVICE_INFO = 0x02,
    VP_CMD_PARAM_LIST = 0x10,
    VP_CMD_PARAM_READ = 0x11,
    VP_CMD_PARAM_WRITE = 0x12,
    VP_CMD_PARAM_SAVE = 0x13,
    VP_CMD_PARAM_LOAD = 0x14,
    VP_CMD_PARAM_DEFAULT = 0x15,
    VP_CMD_TELEMETRY_START = 0x20,
    VP_CMD_TELEMETRY_STOP = 0x21,
    VP_CMD_TELEMETRY_DATA = 0x22,
    VP_CMD_MOTOR_ID_START = 0x30,
    VP_CMD_MOTOR_ID_ABORT = 0x31,
    VP_CMD_MOTOR_ID_PROGRESS = 0x32,
    VP_CMD_PROTECTION_SET = 0x40,
    VP_CMD_FAULT_READ = 0x50,
    VP_CMD_FAULT_CLEAR = 0x51,
    VP_CMD_ARM = 0x60,
    VP_CMD_DISARM = 0x61,
    VP_CMD_STOP = 0x62,
    VP_CMD_SETPOINT = 0x63,
    VP_CMD_SCOPE_CONFIG = 0x70,
    VP_CMD_SCOPE_ARM = 0x71,
    VP_CMD_SCOPE_READ = 0x72,
    VP_CMD_REBOOT = 0x7D,
    VP_CMD_ENTER_DFU = 0x7E,
    VP_CMD_HEARTBEAT = 0x7F,
} vp_cmd_t;

typedef enum {
    VP_STATUS_OK = 0,
    VP_STATUS_NACK_BAD_CRC = 1,
    VP_STATUS_NACK_BAD_LEN = 2,
    VP_STATUS_NACK_UNKNOWN_CMD = 3,
    VP_STATUS_NACK_BAD_PARAM = 4,
    VP_STATUS_NACK_BAD_STATE = 5,
    VP_STATUS_NACK_OUT_OF_BOUNDS = 6,
    VP_STATUS_BUSY = 7,
} vp_status_t;

typedef enum {
    VP_TYPE_U8 = 0,
    VP_TYPE_U16 = 1,
    VP_TYPE_I16 = 2,
    VP_TYPE_U32 = 3,
    VP_TYPE_I32 = 4,
    VP_TYPE_F32 = 5,
    VP_TYPE_ENUM = 6,
} vp_param_type_t;

typedef enum {
    VP_DEVICE_STATE_INIT = 0,
    VP_DEVICE_STATE_PRECHARGE = 1,
    VP_DEVICE_STATE_SELFTEST = 2,
    VP_DEVICE_STATE_STANDBY = 3,
    VP_DEVICE_STATE_ARMED = 4,
    VP_DEVICE_STATE_RUNNING = 5,
    VP_DEVICE_STATE_FAULT = 6,
} vp_device_state_t;

typedef enum {
    VP_SETPOINT_MODE_TORQUE = 0,
    VP_SETPOINT_MODE_SPEED = 1,
} vp_setpoint_mode_t;

typedef enum {
    VP_MOTOR_ID_STAGE_IDLE = 0,
    VP_MOTOR_ID_STAGE_RESISTANCE = 1,
    VP_MOTOR_ID_STAGE_INDUCTANCE = 2,
    VP_MOTOR_ID_STAGE_FLUX = 3,
    VP_MOTOR_ID_STAGE_DONE = 4,
    VP_MOTOR_ID_STAGE_FAILED = 5,
} vp_motor_id_stage_t;

typedef enum {
    VP_TRIG_EDGE_RISING = 0,
    VP_TRIG_EDGE_FALLING = 1,
} vp_trig_edge_t;

/* Fault bit positions and masks (u32 fault mask on the wire) */
#define VP_FAULT_OVERCURRENT_BIT 0u
#define VP_FAULT_OVERCURRENT (1uL << 0)
#define VP_FAULT_OVERVOLTAGE_BIT 1u
#define VP_FAULT_OVERVOLTAGE (1uL << 1)
#define VP_FAULT_UNDERVOLTAGE_BIT 2u
#define VP_FAULT_UNDERVOLTAGE (1uL << 2)
#define VP_FAULT_OVERTEMP_INV_BIT 3u
#define VP_FAULT_OVERTEMP_INV (1uL << 3)
#define VP_FAULT_OVERTEMP_MOTOR_BIT 4u
#define VP_FAULT_OVERTEMP_MOTOR (1uL << 4)
#define VP_FAULT_HALL_FAULT_BIT 5u
#define VP_FAULT_HALL_FAULT (1uL << 5)
#define VP_FAULT_PHASE_LOSS_BIT 6u
#define VP_FAULT_PHASE_LOSS (1uL << 6)
#define VP_FAULT_HEARTBEAT_LOSS_BIT 7u
#define VP_FAULT_HEARTBEAT_LOSS (1uL << 7)
#define VP_FAULT_GATE_DRIVER_BIT 8u
#define VP_FAULT_GATE_DRIVER (1uL << 8)
#define VP_FAULT_SELFTEST_FAIL_BIT 9u
#define VP_FAULT_SELFTEST_FAIL (1uL << 9)
#define VP_FAULT_OVERSPEED_BIT 10u
#define VP_FAULT_OVERSPEED (1uL << 10)
#define VP_FAULT_BRAKE_BACKSTOP_BIT 11u
#define VP_FAULT_BRAKE_BACKSTOP (1uL << 11)

typedef struct {
    uint16_t id;
    const char *name;
    vp_param_type_t type;
    const char *unit;
    float min;
    float max;
    float def_val;
    uint8_t is_nv;   /* 1 = persisted by PARAM_SAVE */
    uint8_t is_rw;   /* 1 = host-writable */
} vp_param_meta_t;

#define VP_PARAM_COUNT 26u
static const vp_param_meta_t VP_PARAMS[VP_PARAM_COUNT] = {
    { 0x0001u, "motor.pole_pairs", VP_TYPE_U8, "", 1.0f, 64.0f, 7.0f, 1u, 1u },
    { 0x0002u, "motor.r_phase", VP_TYPE_F32, "ohm", 0.0005f, 2.0f, 0.02f, 1u, 1u },
    { 0x0003u, "motor.l_d", VP_TYPE_F32, "H", 1e-06f, 0.01f, 2e-05f, 1u, 1u },
    { 0x0004u, "motor.l_q", VP_TYPE_F32, "H", 1e-06f, 0.01f, 2e-05f, 1u, 1u },
    { 0x0005u, "motor.flux_lambda", VP_TYPE_F32, "Wb", 0.0001f, 1.0f, 0.005f, 1u, 1u },
    { 0x0101u, "iloop.kp", VP_TYPE_F32, "V/A", 0.0f, 100.0f, 0.3351f, 1u, 1u },
    { 0x0102u, "iloop.ki", VP_TYPE_F32, "V/(A.s)", 0.0f, 1000000.0f, 335.1f, 1u, 1u },
    { 0x0103u, "iloop.bandwidth_hz", VP_TYPE_F32, "Hz", 2000.0f, 4000.0f, 2666.667f, 1u, 1u },
    { 0x0104u, "iloop.lpf_tf", VP_TYPE_F32, "s", 1e-06f, 0.01f, 1.194e-05f, 1u, 1u },
    { 0x0201u, "prot.overcurrent_a", VP_TYPE_F32, "A", 10.0f, 175.0f, 150.0f, 1u, 1u },
    { 0x0202u, "prot.overvoltage_v", VP_TYPE_F32, "V", 63.5f, 65.5f, 65.0f, 1u, 1u },
    { 0x0301u, "sensor.mode", VP_TYPE_ENUM, "", 0.0f, 2.0f, 0.0f, 1u, 1u },
    { 0x0302u, "sensor.hall_offset_deg", VP_TYPE_F32, "deg", -180.0f, 180.0f, 0.0f, 1u, 1u },
    { 0x0303u, "sensor.hall_sequence", VP_TYPE_U8, "", 0.0f, 5.0f, 0.0f, 1u, 1u },
    { 0x0311u, "sensor.enc_cpr", VP_TYPE_I32, "counts", 1.0f, 1000000.0f, 4096.0f, 1u, 1u },
    { 0x0312u, "sensor.enc_offset_deg", VP_TYPE_F32, "deg", -180.0f, 180.0f, 0.0f, 1u, 1u },
    { 0x0313u, "sensor.enc_direction", VP_TYPE_U8, "", 0.0f, 1.0f, 0.0f, 1u, 1u },
    { 0x0321u, "sensor.obs_gain", VP_TYPE_F32, "", 0.0f, 1000000.0f, 100.0f, 1u, 1u },
    { 0x0401u, "limits.i_max_a", VP_TYPE_F32, "A", 1.0f, 175.0f, 120.0f, 1u, 1u },
    { 0x0402u, "limits.vbus_min_v", VP_TYPE_F32, "V", 15.0f, 60.0f, 20.0f, 1u, 1u },
    { 0x0403u, "limits.vbus_max_v", VP_TYPE_F32, "V", 20.0f, 60.0f, 60.0f, 1u, 1u },
    { 0x0404u, "limits.temp_inv_max_c", VP_TYPE_F32, "degC", 40.0f, 110.0f, 90.0f, 1u, 1u },
    { 0x0405u, "limits.temp_motor_max_c", VP_TYPE_F32, "degC", 40.0f, 180.0f, 120.0f, 1u, 1u },
    { 0x0406u, "limits.speed_max_rpm", VP_TYPE_F32, "rpm", 100.0f, 30000.0f, 5000.0f, 1u, 1u },
    { 0x0501u, "telem.default_mask", VP_TYPE_U32, "", 0.0f, 4294967295.0f, 455.0f, 1u, 1u },
    { 0x0502u, "telem.default_decimation", VP_TYPE_U16, "", 1.0f, 40000.0f, 8.0f, 1u, 1u },
};

typedef struct {
    uint8_t bit;
    const char *name;
    float scale;  /* physical = raw_int16 * scale */
    const char *unit;
} vp_channel_meta_t;

#define VP_CHANNEL_COUNT 18u
static const vp_channel_meta_t VP_CHANNELS[VP_CHANNEL_COUNT] = {
    { 0u, "ia", 0.01f, "A" },
    { 1u, "ib", 0.01f, "A" },
    { 2u, "ic", 0.01f, "A" },
    { 3u, "va", 0.0025f, "V" },
    { 4u, "vb", 0.0025f, "V" },
    { 5u, "vc", 0.0025f, "V" },
    { 6u, "vbus", 0.0025f, "V" },
    { 7u, "id", 0.01f, "A" },
    { 8u, "iq", 0.01f, "A" },
    { 9u, "vd", 0.0025f, "V" },
    { 10u, "vq", 0.0025f, "V" },
    { 11u, "angle_elec", 9.587379924285257e-05f, "rad" },
    { 12u, "speed", 1.0f, "rpm" },
    { 13u, "iq_setpoint", 0.01f, "A" },
    { 14u, "temp_inv1", 0.01f, "degC" },
    { 15u, "temp_inv2", 0.01f, "degC" },
    { 16u, "temp_inv3", 0.01f, "degC" },
    { 17u, "temp_motor", 0.01f, "degC" },
};

#define VP_CH_IA (1uL << 0)
#define VP_CH_IB (1uL << 1)
#define VP_CH_IC (1uL << 2)
#define VP_CH_VA (1uL << 3)
#define VP_CH_VB (1uL << 4)
#define VP_CH_VC (1uL << 5)
#define VP_CH_VBUS (1uL << 6)
#define VP_CH_ID (1uL << 7)
#define VP_CH_IQ (1uL << 8)
#define VP_CH_VD (1uL << 9)
#define VP_CH_VQ (1uL << 10)
#define VP_CH_ANGLE_ELEC (1uL << 11)
#define VP_CH_SPEED (1uL << 12)
#define VP_CH_IQ_SETPOINT (1uL << 13)
#define VP_CH_TEMP_INV1 (1uL << 14)
#define VP_CH_TEMP_INV2 (1uL << 15)
#define VP_CH_TEMP_INV3 (1uL << 16)
#define VP_CH_TEMP_MOTOR (1uL << 17)

/* ------------------------------------------------------------------ */
/* CRC16-CCITT-FALSE: poly 0x1021, init 0xFFFF, no reflect, no xorout */
/* ------------------------------------------------------------------ */
#define VP_CRC_INIT 0xFFFFu

static inline uint16_t vp_crc16(const uint8_t *data, size_t len, uint16_t crc)
{
    size_t i;
    for (i = 0u; i < len; i++) {
        uint8_t bit;
        crc ^= (uint16_t)((uint16_t)data[i] << 8);
        for (bit = 0u; bit < 8u; bit++) {
            if ((crc & 0x8000u) != 0u) {
                crc = (uint16_t)((uint16_t)(crc << 1) ^ 0x1021u);
            } else {
                crc = (uint16_t)(crc << 1);
            }
        }
    }
    return crc;
}

/* ------------------------------------------------------------------ */
/* COBS. dst must hold at least len + len/254 + 1 bytes.              */
/* ------------------------------------------------------------------ */
static inline size_t vp_cobs_encode(uint8_t *dst, const uint8_t *src, size_t len)
{
    size_t out = 1u;      /* index past the pending code byte */
    size_t code_idx = 0u;
    uint8_t code = 1u;
    size_t i;
    for (i = 0u; i < len; i++) {
        if (src[i] == 0u) {
            dst[code_idx] = code;
            code_idx = out;
            out++;
            code = 1u;
        } else {
            dst[out] = src[i];
            out++;
            code++;
            if (code == 0xFFu) {
                dst[code_idx] = code;
                code_idx = out;
                out++;
                code = 1u;
            }
        }
    }
    dst[code_idx] = code;
    return out;
}

/* Returns decoded length, or -1 on malformed input. */
static inline int32_t vp_cobs_decode(uint8_t *dst, const uint8_t *src, size_t len)
{
    size_t in = 0u;
    size_t out = 0u;
    while (in < len) {
        uint8_t code = src[in];
        uint8_t j;
        if (code == 0u) {
            return -1; /* embedded zero */
        }
        in++;
        if ((size_t)(code - 1u) > (len - in)) {
            return -1; /* truncated block */
        }
        for (j = 1u; j < code; j++) {
            if (src[in] == 0u) {
                return -1; /* embedded zero in block */
            }
            dst[out] = src[in];
            out++;
            in++;
        }
        if ((code != 0xFFu) && (in < len)) {
            dst[out] = 0u;
            out++;
        }
    }
    return (int32_t)out;
}

/* ------------------------------------------------------------------ */
/* Frame: [SYNC][VER][FLAGS][CMD][SEQ][LEN u16 LE][PAYLOAD][CRC16 LE] */
/* CRC over VER..PAYLOAD. Wire form = COBS(frame) + 0x00 delimiter.   */
/* ------------------------------------------------------------------ */
#define VP_FRAME_OVERHEAD 9u
#define VP_MAX_FRAME (VP_FRAME_OVERHEAD + VP_MAX_PAYLOAD)
/* COBS worst case: +1 byte per 254, +1 code byte, +1 wire delimiter */
#define VP_MAX_WIRE (VP_MAX_FRAME + (VP_MAX_FRAME / 254u) + 2u)

typedef struct {
    uint8_t ver;
    uint8_t flags;
    uint8_t cmd;
    uint8_t seq;
    uint16_t len;
    const uint8_t *payload; /* points into the decoder's buffer; copy before next feed */
} vp_frame_t;

/* Returns frame size, or -1 if cap is too small / payload too long. */
static inline int32_t vp_encode_frame(uint8_t *dst, size_t cap, uint8_t cmd,
                                      uint8_t seq, uint8_t flags,
                                      const uint8_t *payload, uint16_t len)
{
    uint16_t crc;
    size_t total = (size_t)VP_FRAME_OVERHEAD + (size_t)len;
    if ((len > VP_MAX_PAYLOAD) || (cap < total)) {
        return -1;
    }
    dst[0] = VP_SYNC;
    dst[1] = VP_PROTOCOL_VERSION_MAJOR;
    dst[2] = flags;
    dst[3] = cmd;
    dst[4] = seq;
    dst[5] = (uint8_t)(len & 0xFFu);
    dst[6] = (uint8_t)(len >> 8);
    if ((len > 0u) && (payload != NULL)) {
        (void)memcpy(&dst[7], payload, (size_t)len);
    }
    crc = vp_crc16(&dst[1], 6u + (size_t)len, VP_CRC_INIT);
    dst[7u + len] = (uint8_t)(crc & 0xFFu);
    dst[8u + len] = (uint8_t)(crc >> 8);
    return (int32_t)total;
}

/* Encodes frame + COBS + 0x00 delimiter into dst. Returns wire size or -1. */
static inline int32_t vp_encode_wire(uint8_t *dst, size_t cap, uint8_t cmd,
                                     uint8_t seq, uint8_t flags,
                                     const uint8_t *payload, uint16_t len)
{
    uint8_t frame[VP_MAX_FRAME];
    int32_t fsize = vp_encode_frame(frame, sizeof frame, cmd, seq, flags, payload, len);
    size_t wsize;
    if (fsize < 0) {
        return -1;
    }
    if (cap < ((size_t)fsize + ((size_t)fsize / 254u) + 2u)) {
        return -1;
    }
    wsize = vp_cobs_encode(dst, frame, (size_t)fsize);
    dst[wsize] = 0u;
    return (int32_t)(wsize + 1u);
}

/* Streaming decoder. No dynamic allocation; safe to feed from any context
 * EXCEPT the control ISR (frame handling belongs in the main loop). */
typedef struct {
    uint8_t buf[VP_MAX_WIRE];     /* raw COBS bytes of the current packet */
    uint16_t len;
    uint8_t overflow;             /* dropping until next delimiter */
    uint8_t decoded[VP_MAX_FRAME];
    uint16_t crc_errors;
    uint16_t len_errors;
    uint16_t cobs_errors;
    uint16_t sync_errors;
    uint16_t overflow_errors;
} vp_decoder_t;

static inline void vp_decoder_init(vp_decoder_t *d)
{
    (void)memset(d, 0, sizeof *d);
}

/* Feed one byte. Returns 1 when *out holds a complete valid frame
 * (out->payload points into d->decoded and is valid until the next feed
 * that completes a packet), else 0. Malformed packets are counted+dropped. */
static inline int vp_decoder_feed(vp_decoder_t *d, uint8_t byte, vp_frame_t *out)
{
    int32_t raw_len;
    uint16_t length;
    uint16_t crc_rx;
    uint16_t crc_calc;

    if (byte != 0u) {
        if (d->overflow != 0u) {
            return 0;
        }
        if (d->len >= (uint16_t)sizeof d->buf) {
            d->overflow = 1u;
            d->overflow_errors++;
            return 0;
        }
        d->buf[d->len] = byte;
        d->len++;
        return 0;
    }

    /* 0x00 delimiter: close out the packet */
    if (d->overflow != 0u) {
        d->overflow = 0u;
        d->len = 0u;
        return 0;
    }
    if (d->len == 0u) {
        return 0; /* idle delimiter */
    }
    raw_len = vp_cobs_decode(d->decoded, d->buf, (size_t)d->len);
    d->len = 0u;
    if (raw_len < 0) {
        d->cobs_errors++;
        return 0;
    }
    if (raw_len < (int32_t)VP_FRAME_OVERHEAD) {
        d->len_errors++;
        return 0;
    }
    if (d->decoded[0] != VP_SYNC) {
        d->sync_errors++;
        return 0;
    }
    length = (uint16_t)((uint16_t)d->decoded[5] | ((uint16_t)d->decoded[6] << 8));
    if ((int32_t)length != (raw_len - (int32_t)VP_FRAME_OVERHEAD)) {
        d->len_errors++;
        return 0;
    }
    crc_rx = (uint16_t)((uint16_t)d->decoded[7u + length] |
                        ((uint16_t)d->decoded[8u + length] << 8));
    crc_calc = vp_crc16(&d->decoded[1], 6u + (size_t)length, VP_CRC_INIT);
    if (crc_rx != crc_calc) {
        d->crc_errors++;
        return 0;
    }
    out->ver = d->decoded[1];
    out->flags = d->decoded[2];
    out->cmd = d->decoded[3];
    out->seq = d->decoded[4];
    out->len = length;
    out->payload = &d->decoded[7];
    return 1;
}

#endif /* VORTEX_PROTOCOL_H */
