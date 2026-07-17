#include "vx_nv_store.h"

#include <string.h>

#include "vortex_protocol.h" /* vp_crc16 */

/* Reads and validates one slot. Returns payload len (>=0) and seq,
 * or -1 if the slot holds no valid record. */
static int32_t slot_scan(const vx_nv_ops_t *ops, uint8_t slot, uint32_t *seq_out)
{
    uint8_t hdr[VX_NV_HEADER_SIZE];
    uint32_t magic;
    uint32_t seq;
    uint16_t len;
    uint16_t crc_rx;
    uint16_t crc;
    uint8_t chunk[32];
    uint32_t off;
    uint32_t remaining;

    if (!ops->read(ops->ctx, slot, 0u, hdr, sizeof hdr)) {
        return -1;
    }
    magic = (uint32_t)hdr[0] | ((uint32_t)hdr[1] << 8) |
            ((uint32_t)hdr[2] << 16) | ((uint32_t)hdr[3] << 24);
    if (magic != VX_NV_MAGIC) {
        return -1;
    }
    seq = (uint32_t)hdr[4] | ((uint32_t)hdr[5] << 8) |
          ((uint32_t)hdr[6] << 16) | ((uint32_t)hdr[7] << 24);
    len = (uint16_t)((uint16_t)hdr[8] | ((uint16_t)hdr[9] << 8));
    if (((uint32_t)len + VX_NV_OVERHEAD) > ops->slot_size) {
        return -1;
    }

    /* CRC over seq..payload (header bytes 4..9 + payload) */
    crc = vp_crc16(&hdr[4], 6u, VP_CRC_INIT);
    off = VX_NV_HEADER_SIZE;
    remaining = len;
    while (remaining > 0u) {
        uint32_t n = (remaining > sizeof chunk) ? (uint32_t)sizeof chunk : remaining;
        if (!ops->read(ops->ctx, slot, off, chunk, n)) {
            return -1;
        }
        crc = vp_crc16(chunk, n, crc);
        off += n;
        remaining -= n;
    }
    if (!ops->read(ops->ctx, slot, off, chunk, 2u)) {
        return -1;
    }
    crc_rx = (uint16_t)((uint16_t)chunk[0] | ((uint16_t)chunk[1] << 8));
    if (crc_rx != crc) {
        return -1;
    }
    *seq_out = seq;
    return (int32_t)len;
}

/* Newest valid slot, or -1 if none. */
static int8_t newest_slot(const vx_nv_ops_t *ops, uint32_t *seq_out, int32_t *len_out)
{
    uint32_t seq0 = 0u;
    uint32_t seq1 = 0u;
    int32_t len0 = slot_scan(ops, 0u, &seq0);
    int32_t len1 = slot_scan(ops, 1u, &seq1);

    if ((len0 < 0) && (len1 < 0)) {
        return -1;
    }
    /* signed diff handles seq wraparound */
    if ((len1 < 0) || ((len0 >= 0) && ((int32_t)(seq0 - seq1) > 0))) {
        *seq_out = seq0;
        *len_out = len0;
        return 0;
    }
    *seq_out = seq1;
    *len_out = len1;
    return 1;
}

bool vx_nv_save(const vx_nv_ops_t *ops, const uint8_t *data, uint16_t len)
{
    uint8_t hdr[VX_NV_HEADER_SIZE];
    uint8_t crc_bytes[2];
    uint16_t crc;
    uint32_t seq = 1u;
    int32_t cur_len;
    uint8_t target = 0u;
    int8_t newest = newest_slot(ops, &seq, &cur_len);

    if (((uint32_t)len + VX_NV_OVERHEAD) > ops->slot_size) {
        return false;
    }
    if (newest >= 0) {
        target = (uint8_t)(1 - newest);
        seq = seq + 1u;
    }

    hdr[0] = (uint8_t)(VX_NV_MAGIC & 0xFFu);
    hdr[1] = (uint8_t)((VX_NV_MAGIC >> 8) & 0xFFu);
    hdr[2] = (uint8_t)((VX_NV_MAGIC >> 16) & 0xFFu);
    hdr[3] = (uint8_t)((VX_NV_MAGIC >> 24) & 0xFFu);
    hdr[4] = (uint8_t)(seq & 0xFFu);
    hdr[5] = (uint8_t)((seq >> 8) & 0xFFu);
    hdr[6] = (uint8_t)((seq >> 16) & 0xFFu);
    hdr[7] = (uint8_t)((seq >> 24) & 0xFFu);
    hdr[8] = (uint8_t)(len & 0xFFu);
    hdr[9] = (uint8_t)(len >> 8);
    crc = vp_crc16(&hdr[4], 6u, VP_CRC_INIT);
    crc = vp_crc16(data, len, crc);
    crc_bytes[0] = (uint8_t)(crc & 0xFFu);
    crc_bytes[1] = (uint8_t)(crc >> 8);

    if (!ops->erase(ops->ctx, target)) {
        return false;
    }
    /* Payload + CRC first, magic header LAST: a record only becomes
     * discoverable once it is complete, so power loss mid-save leaves the
     * other slot's record authoritative. */
    if (!ops->write(ops->ctx, target, VX_NV_HEADER_SIZE, data, len)) {
        return false;
    }
    if (!ops->write(ops->ctx, target, VX_NV_HEADER_SIZE + (uint32_t)len,
                    crc_bytes, 2u)) {
        return false;
    }
    return ops->write(ops->ctx, target, 0u, hdr, sizeof hdr);
}

int32_t vx_nv_load(const vx_nv_ops_t *ops, uint8_t *data, uint16_t cap)
{
    uint32_t seq;
    int32_t len;
    int8_t slot = newest_slot(ops, &seq, &len);

    if ((slot < 0) || (len > (int32_t)cap)) {
        return -1;
    }
    if (!ops->read(ops->ctx, (uint8_t)slot, VX_NV_HEADER_SIZE, data, (size_t)len)) {
        return -1;
    }
    return len;
}
