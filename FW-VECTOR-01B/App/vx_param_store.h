/* vx_param_store.h — runtime parameter table over VP_PARAMS metadata.
 *
 * Values are held as float regardless of wire type (26 params, worst case
 * exactly representable: u32 masks <= 2^24 in practice — telem.default_mask
 * fits). Wire encoding/decoding follows the param's declared type.
 * Bounds and RO enforcement here is the single write path for both
 * PARAM_WRITE and PROTECTION_SET.
 */
#ifndef VX_PARAM_STORE_H
#define VX_PARAM_STORE_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "vortex_protocol.h"

typedef struct {
    float values[VP_PARAM_COUNT];
} vx_params_t;

/* Serialized NV blob: [magic u32][count u16][(id u16, f32) x count][crc16] */
#define VX_PARAM_NV_MAGIC 0x564E5850u /* "PXNV" LE */
#define VX_PARAM_NV_MAX_SIZE (4u + 2u + (VP_PARAM_COUNT * 6u) + 2u)

int32_t vx_param_index(uint16_t id); /* -1 if unknown */
void vx_params_defaults(vx_params_t *p);

uint8_t vx_param_value_size(vp_param_type_t type);
/* Returns bytes written (1/2/4). dst must hold 4 bytes. */
uint8_t vx_param_encode_value(const vp_param_meta_t *m, float value, uint8_t *dst);
/* false if len does not match the type's wire size. */
bool vx_param_decode_value(const vp_param_meta_t *m, const uint8_t *src,
                           uint16_t len, float *out);

vp_status_t vx_param_read(const vx_params_t *p, uint16_t id, float *out);
/* VP_STATUS_NACK_BAD_PARAM for unknown/RO id,
 * VP_STATUS_NACK_OUT_OF_BOUNDS outside min..max. */
vp_status_t vx_param_write(vx_params_t *p, uint16_t id, float value);

/* NV-flagged params only. Returns blob size, or 0 if cap too small. */
size_t vx_params_nv_serialize(const vx_params_t *p, uint8_t *buf, size_t cap);
/* Tolerant load: unknown ids skipped, out-of-bounds values rejected
 * per-entry. false = blob invalid (magic/CRC/size), p untouched. */
bool vx_params_nv_deserialize(vx_params_t *p, const uint8_t *buf, size_t len);

#endif /* VX_PARAM_STORE_H */
