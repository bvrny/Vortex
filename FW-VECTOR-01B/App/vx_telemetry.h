/* vx_telemetry.h — telemetry batch payload builder (PROTOCOL.md §4).
 *
 * Builds TELEMETRY_DATA payloads (also the capture format served by
 * SCOPE_READ) sample by sample into a fixed buffer. The producer decides
 * when to flush: either when vx_telem_add() reports full or when the
 * u16 t_offset would overflow (>65.5 ms after base).
 */
#ifndef VX_TELEMETRY_H
#define VX_TELEMETRY_H

#include <stdbool.h>
#include <stdint.h>

#include "vortex_protocol.h"

#define VX_TELEM_HEADER_SIZE 12u

typedef struct {
    uint8_t buf[VP_MAX_PAYLOAD];
    uint16_t len;
    uint16_t n_samples;
    uint8_t nch;
} vx_telem_t;

uint8_t vx_popcount32(uint32_t v);

/* Raw wire value for a physical reading, clamped to int16. */
int16_t vx_telem_encode(float phys, float scale);

void vx_telem_begin(vx_telem_t *t, uint32_t base_us, uint32_t mask,
                    uint16_t decimation);

/* Append one sample (raw[nch] in ascending mask-bit order).
 * false = batch full, flush and begin a new one. */
bool vx_telem_add(vx_telem_t *t, uint16_t t_offset_us, const int16_t *raw);

/* Finalize (patch n_samples) and expose the payload. */
const uint8_t *vx_telem_payload(vx_telem_t *t, uint16_t *len);

/* Samples that fit one batch for a given mask. */
uint16_t vx_telem_max_samples(uint32_t mask);

#endif /* VX_TELEMETRY_H */
