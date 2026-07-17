/* vx_usb_tx.h — USB CDC transmit batching with ZLP handling.
 *
 * Whole wire frames are queued all-or-nothing into an SPSC ring (producer:
 * main loop; consumer: USB TX-complete ISR requesting the next packet).
 * Batching: each packet carries up to 64 bytes regardless of frame
 * boundaries — COBS delimiters keep the receiver in sync. If a transfer
 * ends on an exactly-full packet, a zero-length packet must follow so the
 * host does not hold the transfer open; vx_usb_tx_next() reports it.
 */
#ifndef VX_USB_TX_H
#define VX_USB_TX_H

#include <stdbool.h>
#include <stdint.h>

#include "vx_spsc.h"

#define VX_USB_PKT_SIZE 64u

typedef struct {
    vx_spsc_t ring;
    bool zlp_pending;
} vx_usb_tx_t;

static inline bool vx_usb_tx_init(vx_usb_tx_t *t, uint8_t *storage,
                                  uint16_t capacity)
{
    t->zlp_pending = false;
    return vx_spsc_init(&t->ring, storage, capacity);
}

/* Queue one complete wire frame. false = no room (frame dropped whole;
 * the host recovers by request timeout + retry). */
static inline bool vx_usb_tx_queue(vx_usb_tx_t *t, const uint8_t *data,
                                   uint16_t len)
{
    return vx_spsc_push_all(&t->ring, data, len);
}

/* Fill the next packet to hand to the USB stack.
 * Returns true when a packet should be sent; *len may be 0 (ZLP). */
static inline bool vx_usb_tx_next(vx_usb_tx_t *t, uint8_t *pkt, uint16_t *len)
{
    uint16_t n = vx_spsc_pop_many(&t->ring, pkt, VX_USB_PKT_SIZE);
    if (n == 0u) {
        if (t->zlp_pending) {
            t->zlp_pending = false;
            *len = 0u;
            return true;
        }
        return false;
    }
    t->zlp_pending = (n == VX_USB_PKT_SIZE) && (vx_spsc_count(&t->ring) == 0u);
    *len = n;
    return true;
}

#endif /* VX_USB_TX_H */
