/* vx_nv_store.h — ping-pong non-volatile record store.
 *
 * Two flash slots (spec: STM32G4 bank-2 high-endurance pages) alternate:
 * a save erases + writes the slot NOT holding the newest valid record, so
 * power loss mid-write always leaves the previous record intact. Flash
 * access goes through vx_nv_ops_t so host tests run against RAM.
 *
 * Slot layout: [magic u32][seq u32][len u16][payload][crc16 over seq..payload]
 */
#ifndef VX_NV_STORE_H
#define VX_NV_STORE_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define VX_NV_MAGIC 0x564E5652u /* "RVNV" LE */
#define VX_NV_HEADER_SIZE 10u
#define VX_NV_OVERHEAD (VX_NV_HEADER_SIZE + 2u)

typedef struct {
    bool (*erase)(void *ctx, uint8_t slot);              /* slot 0 or 1 */
    bool (*write)(void *ctx, uint8_t slot, uint32_t offset,
                  const uint8_t *data, size_t len);
    bool (*read)(void *ctx, uint8_t slot, uint32_t offset,
                 uint8_t *data, size_t len);
    uint32_t slot_size;
    void *ctx;
} vx_nv_ops_t;

/* Write a new record (seq = newest + 1) into the older slot.
 * false on flash error or len too large for a slot. */
bool vx_nv_save(const vx_nv_ops_t *ops, const uint8_t *data, uint16_t len);

/* Load the newest valid record's payload. Returns payload length,
 * or -1 if no valid record exists / cap too small. */
int32_t vx_nv_load(const vx_nv_ops_t *ops, uint8_t *data, uint16_t cap);

#endif /* VX_NV_STORE_H */
