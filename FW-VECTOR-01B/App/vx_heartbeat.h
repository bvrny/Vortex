/* vx_heartbeat.h — host heartbeat watchdog (PROTOCOL.md §5).
 *
 * Armed/running only: if no HEARTBEAT frame arrives within
 * VP_HEARTBEAT_TIMEOUT_MS the device must disarm and latch HEARTBEAT_LOSS.
 * Millisecond tick wraps naturally with unsigned arithmetic.
 */
#ifndef VX_HEARTBEAT_H
#define VX_HEARTBEAT_H

#include <stdbool.h>
#include <stdint.h>

#include "vortex_protocol.h"

typedef struct {
    uint32_t last_ms;
    bool watching;
} vx_heartbeat_t;

static inline void vx_hb_init(vx_heartbeat_t *hb)
{
    hb->last_ms = 0u;
    hb->watching = false;
}

/* Call on ARM: starts the watch window from now. */
static inline void vx_hb_start(vx_heartbeat_t *hb, uint32_t now_ms)
{
    hb->last_ms = now_ms;
    hb->watching = true;
}

/* Call on DISARM/STOP/fault: heartbeat no longer required. */
static inline void vx_hb_stop(vx_heartbeat_t *hb)
{
    hb->watching = false;
}

/* Call on every received HEARTBEAT frame. */
static inline void vx_hb_feed(vx_heartbeat_t *hb, uint32_t now_ms)
{
    hb->last_ms = now_ms;
}

static inline bool vx_hb_expired(const vx_heartbeat_t *hb, uint32_t now_ms)
{
    return hb->watching && ((uint32_t)(now_ms - hb->last_ms) > VP_HEARTBEAT_TIMEOUT_MS);
}

#endif /* VX_HEARTBEAT_H */
