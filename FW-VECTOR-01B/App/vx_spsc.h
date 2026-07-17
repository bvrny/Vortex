/* vx_spsc.h — single-producer/single-consumer byte ring buffer.
 *
 * Lock-free for one producer context and one consumer context (e.g. USB RX
 * ISR -> main loop). Capacity must be a power of two; one slot is kept free
 * to distinguish full from empty.
 */
#ifndef VX_SPSC_H
#define VX_SPSC_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

typedef struct {
    uint8_t *buf;
    uint16_t mask;                 /* capacity - 1 */
    volatile uint16_t head;        /* producer writes */
    volatile uint16_t tail;        /* consumer writes */
} vx_spsc_t;

/* capacity must be a power of two >= 2. Returns false otherwise. */
static inline bool vx_spsc_init(vx_spsc_t *q, uint8_t *storage, uint16_t capacity)
{
    if ((capacity < 2u) || ((capacity & (uint16_t)(capacity - 1u)) != 0u)) {
        return false;
    }
    q->buf = storage;
    q->mask = (uint16_t)(capacity - 1u);
    q->head = 0u;
    q->tail = 0u;
    return true;
}

static inline uint16_t vx_spsc_count(const vx_spsc_t *q)
{
    return (uint16_t)((uint16_t)(q->head - q->tail) & q->mask);
}

static inline uint16_t vx_spsc_free(const vx_spsc_t *q)
{
    return (uint16_t)(q->mask - vx_spsc_count(q));
}

static inline bool vx_spsc_push(vx_spsc_t *q, uint8_t byte)
{
    uint16_t head = q->head;
    uint16_t next = (uint16_t)((head + 1u) & q->mask);
    if (next == q->tail) {
        return false; /* full */
    }
    q->buf[head] = byte;
    q->head = next;
    return true;
}

static inline bool vx_spsc_pop(vx_spsc_t *q, uint8_t *byte)
{
    uint16_t tail = q->tail;
    if (tail == q->head) {
        return false; /* empty */
    }
    *byte = q->buf[tail];
    q->tail = (uint16_t)((tail + 1u) & q->mask);
    return true;
}

/* All-or-nothing bulk push: never leaves a partial record in the queue. */
static inline bool vx_spsc_push_all(vx_spsc_t *q, const uint8_t *data, uint16_t len)
{
    uint16_t i;
    if (vx_spsc_free(q) < len) {
        return false;
    }
    for (i = 0u; i < len; i++) {
        (void)vx_spsc_push(q, data[i]);
    }
    return true;
}

static inline uint16_t vx_spsc_pop_many(vx_spsc_t *q, uint8_t *dst, uint16_t max)
{
    uint16_t n = 0u;
    while ((n < max) && vx_spsc_pop(q, &dst[n])) {
        n++;
    }
    return n;
}

#endif /* VX_SPSC_H */
