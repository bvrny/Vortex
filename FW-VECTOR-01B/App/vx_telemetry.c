#include "vx_telemetry.h"

uint8_t vx_popcount32(uint32_t v)
{
    uint8_t n = 0u;
    while (v != 0u) {
        v &= v - 1u;
        n++;
    }
    return n;
}

int16_t vx_telem_encode(float phys, float scale)
{
    float raw = phys / scale;
    if (raw >= 32767.0f) {
        return 32767;
    }
    if (raw <= -32768.0f) {
        return -32768;
    }
    return (int16_t)((raw >= 0.0f) ? (raw + 0.5f) : (raw - 0.5f));
}

void vx_telem_begin(vx_telem_t *t, uint32_t base_us, uint32_t mask,
                    uint16_t decimation)
{
    t->buf[0] = (uint8_t)(base_us & 0xFFu);
    t->buf[1] = (uint8_t)((base_us >> 8) & 0xFFu);
    t->buf[2] = (uint8_t)((base_us >> 16) & 0xFFu);
    t->buf[3] = (uint8_t)((base_us >> 24) & 0xFFu);
    t->buf[4] = (uint8_t)(mask & 0xFFu);
    t->buf[5] = (uint8_t)((mask >> 8) & 0xFFu);
    t->buf[6] = (uint8_t)((mask >> 16) & 0xFFu);
    t->buf[7] = (uint8_t)((mask >> 24) & 0xFFu);
    t->buf[8] = 0u;  /* n_samples patched in vx_telem_payload */
    t->buf[9] = 0u;
    t->buf[10] = (uint8_t)(decimation & 0xFFu);
    t->buf[11] = (uint8_t)(decimation >> 8);
    t->len = VX_TELEM_HEADER_SIZE;
    t->n_samples = 0u;
    t->nch = vx_popcount32(mask);
}

bool vx_telem_add(vx_telem_t *t, uint16_t t_offset_us, const int16_t *raw)
{
    uint16_t sample_size = (uint16_t)(2u + (2u * (uint16_t)t->nch));
    uint8_t i;

    if (((uint32_t)t->len + sample_size) > VP_MAX_PAYLOAD) {
        return false;
    }
    t->buf[t->len] = (uint8_t)(t_offset_us & 0xFFu);
    t->buf[t->len + 1u] = (uint8_t)(t_offset_us >> 8);
    t->len = (uint16_t)(t->len + 2u);
    for (i = 0u; i < t->nch; i++) {
        uint16_t u = (uint16_t)raw[i];
        t->buf[t->len] = (uint8_t)(u & 0xFFu);
        t->buf[t->len + 1u] = (uint8_t)(u >> 8);
        t->len = (uint16_t)(t->len + 2u);
    }
    t->n_samples++;
    return true;
}

const uint8_t *vx_telem_payload(vx_telem_t *t, uint16_t *len)
{
    t->buf[8] = (uint8_t)(t->n_samples & 0xFFu);
    t->buf[9] = (uint8_t)(t->n_samples >> 8);
    *len = t->len;
    return t->buf;
}

uint16_t vx_telem_max_samples(uint32_t mask)
{
    uint16_t sample_size = (uint16_t)(2u + (2u * (uint16_t)vx_popcount32(mask)));
    return (uint16_t)((VP_MAX_PAYLOAD - VX_TELEM_HEADER_SIZE) / sample_size);
}
