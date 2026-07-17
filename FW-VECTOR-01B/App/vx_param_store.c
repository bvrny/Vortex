#include "vx_param_store.h"

#include <string.h>

int32_t vx_param_index(uint16_t id)
{
    uint32_t i;
    for (i = 0u; i < VP_PARAM_COUNT; i++) {
        if (VP_PARAMS[i].id == id) {
            return (int32_t)i;
        }
    }
    return -1;
}

void vx_params_defaults(vx_params_t *p)
{
    uint32_t i;
    for (i = 0u; i < VP_PARAM_COUNT; i++) {
        p->values[i] = VP_PARAMS[i].def_val;
    }
}

uint8_t vx_param_value_size(vp_param_type_t type)
{
    switch (type) {
    case VP_TYPE_U8:
    case VP_TYPE_ENUM:
        return 1u;
    case VP_TYPE_U16:
    case VP_TYPE_I16:
        return 2u;
    default: /* U32, I32, F32 */
        return 4u;
    }
}

static int32_t round_to_i32(float v)
{
    return (v >= 0.0f) ? (int32_t)(v + 0.5f) : (int32_t)(v - 0.5f);
}

uint8_t vx_param_encode_value(const vp_param_meta_t *m, float value, uint8_t *dst)
{
    uint8_t size = vx_param_value_size(m->type);
    uint32_t u = 0u;

    if (m->type == VP_TYPE_F32) {
        (void)memcpy(&u, &value, 4u);
    } else if (m->type == VP_TYPE_U32) {
        u = (uint32_t)(value + 0.5f); /* stays valid above int32 range */
    } else {
        u = (uint32_t)round_to_i32(value);
    }
    dst[0] = (uint8_t)(u & 0xFFu);
    if (size >= 2u) {
        dst[1] = (uint8_t)((u >> 8) & 0xFFu);
    }
    if (size == 4u) {
        dst[2] = (uint8_t)((u >> 16) & 0xFFu);
        dst[3] = (uint8_t)((u >> 24) & 0xFFu);
    }
    return size;
}

bool vx_param_decode_value(const vp_param_meta_t *m, const uint8_t *src,
                           uint16_t len, float *out)
{
    uint8_t size = vx_param_value_size(m->type);
    uint32_t u = 0u;
    uint8_t i;

    if (len != size) {
        return false;
    }
    for (i = 0u; i < size; i++) {
        u |= ((uint32_t)src[i]) << (8u * i);
    }
    switch (m->type) {
    case VP_TYPE_F32: {
        float f;
        (void)memcpy(&f, &u, 4u);
        *out = f;
        break;
    }
    case VP_TYPE_I16:
        *out = (float)(int16_t)u;
        break;
    case VP_TYPE_I32:
        *out = (float)(int32_t)u;
        break;
    default: /* unsigned */
        *out = (float)u;
        break;
    }
    return true;
}

vp_status_t vx_param_read(const vx_params_t *p, uint16_t id, float *out)
{
    int32_t idx = vx_param_index(id);
    if (idx < 0) {
        return VP_STATUS_NACK_BAD_PARAM;
    }
    *out = p->values[idx];
    return VP_STATUS_OK;
}

vp_status_t vx_param_write(vx_params_t *p, uint16_t id, float value)
{
    int32_t idx = vx_param_index(id);
    if ((idx < 0) || (VP_PARAMS[idx].is_rw == 0u)) {
        return VP_STATUS_NACK_BAD_PARAM;
    }
    if ((value < VP_PARAMS[idx].min) || (value > VP_PARAMS[idx].max)) {
        return VP_STATUS_NACK_OUT_OF_BOUNDS;
    }
    p->values[idx] = value;
    return VP_STATUS_OK;
}

size_t vx_params_nv_serialize(const vx_params_t *p, uint8_t *buf, size_t cap)
{
    size_t pos = 6u; /* magic + count, patched below */
    uint16_t count = 0u;
    uint16_t crc;
    uint32_t i;

    if (cap < VX_PARAM_NV_MAX_SIZE) {
        return 0u;
    }
    buf[0] = (uint8_t)(VX_PARAM_NV_MAGIC & 0xFFu);
    buf[1] = (uint8_t)((VX_PARAM_NV_MAGIC >> 8) & 0xFFu);
    buf[2] = (uint8_t)((VX_PARAM_NV_MAGIC >> 16) & 0xFFu);
    buf[3] = (uint8_t)((VX_PARAM_NV_MAGIC >> 24) & 0xFFu);
    for (i = 0u; i < VP_PARAM_COUNT; i++) {
        if (VP_PARAMS[i].is_nv == 0u) {
            continue;
        }
        buf[pos] = (uint8_t)(VP_PARAMS[i].id & 0xFFu);
        buf[pos + 1u] = (uint8_t)(VP_PARAMS[i].id >> 8);
        (void)memcpy(&buf[pos + 2u], &p->values[i], 4u);
        pos += 6u;
        count++;
    }
    buf[4] = (uint8_t)(count & 0xFFu);
    buf[5] = (uint8_t)(count >> 8);
    crc = vp_crc16(buf, pos, VP_CRC_INIT);
    buf[pos] = (uint8_t)(crc & 0xFFu);
    buf[pos + 1u] = (uint8_t)(crc >> 8);
    return pos + 2u;
}

bool vx_params_nv_deserialize(vx_params_t *p, const uint8_t *buf, size_t len)
{
    uint32_t magic;
    uint16_t count;
    uint16_t crc_rx;
    uint16_t crc_calc;
    size_t pos;
    uint16_t n;

    if (len < 8u) {
        return false;
    }
    magic = (uint32_t)buf[0] | ((uint32_t)buf[1] << 8) |
            ((uint32_t)buf[2] << 16) | ((uint32_t)buf[3] << 24);
    if (magic != VX_PARAM_NV_MAGIC) {
        return false;
    }
    count = (uint16_t)((uint16_t)buf[4] | ((uint16_t)buf[5] << 8));
    if (len != (6u + ((size_t)count * 6u) + 2u)) {
        return false;
    }
    crc_rx = (uint16_t)((uint16_t)buf[len - 2u] | ((uint16_t)buf[len - 1u] << 8));
    crc_calc = vp_crc16(buf, len - 2u, VP_CRC_INIT);
    if (crc_rx != crc_calc) {
        return false;
    }
    pos = 6u;
    for (n = 0u; n < count; n++) {
        uint16_t id = (uint16_t)((uint16_t)buf[pos] | ((uint16_t)buf[pos + 1u] << 8));
        float value;
        int32_t idx = vx_param_index(id);
        (void)memcpy(&value, &buf[pos + 2u], 4u);
        /* Unknown id (blob from another fw rev) or out-of-bounds value:
         * skip the entry, keep the rest. */
        if ((idx >= 0) && (value >= VP_PARAMS[idx].min) &&
            (value <= VP_PARAMS[idx].max)) {
            p->values[idx] = value;
        }
        pos += 6u;
    }
    return true;
}
