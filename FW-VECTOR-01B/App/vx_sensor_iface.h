/* vx_sensor_iface.h — position/speed sensor abstraction.
 *
 * The FOC loop consumes electrical angle + speed through this interface so
 * the Hall-interpolation implementation (spec: Hall-only position sensing)
 * can be swapped for a host-test stub. Implementations must be callable
 * from the control ISR: no blocking, no allocation.
 */
#ifndef VX_SENSOR_IFACE_H
#define VX_SENSOR_IFACE_H

#include <stdbool.h>
#include <stdint.h>

typedef struct {
    /* Electrical angle in rad [0, 2*pi); false while not yet valid
     * (e.g. before the first Hall transition after boot). */
    bool (*angle_elec)(void *ctx, float *rad);
    /* Mechanical speed in rpm (signed). */
    bool (*speed_rpm)(void *ctx, float *rpm);
    /* false on sensor fault (illegal Hall code, stalled interpolation). */
    bool (*healthy)(void *ctx);
    void *ctx;
} vx_sensor_iface_t;

#endif /* VX_SENSOR_IFACE_H */
