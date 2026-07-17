/* Host tests for FW-VECTOR-01B/App modules. Build + run:
 *   cmake -B build && cmake --build build && ctest --test-dir build
 * or: gcc -std=c11 -Wall -Wextra -I../App -I../../PROTO-VORTEX-01A/generated \
 *       test_app.c ../App/vx_*.c -lm -o test_app && ./test_app
 */
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <string.h>

#include "vortex_protocol.h"
#include "vx_device.h"
#include "vx_heartbeat.h"
#include "vx_motor_id.h"
#include "vx_nv_store.h"
#include "vx_param_store.h"
#include "vx_protection.h"
#include "vx_spsc.h"
#include "vx_telemetry.h"
#include "vx_usb_tx.h"

#define APPROX(a, b, tol) (fabsf((a) - (b)) <= (tol))

/* ------------------------------------------------------------ spsc */

static void test_spsc(void)
{
    uint8_t storage[16];
    vx_spsc_t q;
    uint8_t b = 0u;
    uint8_t big[15];

    assert(!vx_spsc_init(&q, storage, 10u)); /* not a power of two */
    assert(vx_spsc_init(&q, storage, 16u));
    assert(vx_spsc_count(&q) == 0u);
    assert(!vx_spsc_pop(&q, &b));

    assert(vx_spsc_push(&q, 0xAAu));
    assert(vx_spsc_count(&q) == 1u);
    assert(vx_spsc_pop(&q, &b) && (b == 0xAAu));

    /* fill to capacity-1, then full */
    for (int i = 0; i < 15; i++) {
        assert(vx_spsc_push(&q, (uint8_t)i));
    }
    assert(!vx_spsc_push(&q, 0xFFu));
    /* wrap: drain two, push two */
    assert(vx_spsc_pop(&q, &b) && (b == 0u));
    assert(vx_spsc_pop(&q, &b) && (b == 1u));
    assert(vx_spsc_push(&q, 100u) && vx_spsc_push(&q, 101u));
    assert(!vx_spsc_push(&q, 102u));

    /* atomic bulk push: no room -> nothing enqueued */
    memset(big, 7, sizeof big);
    assert(!vx_spsc_push_all(&q, big, 3u));
    assert(vx_spsc_count(&q) == 15u);
    printf("spsc ok\n");
}

/* ------------------------------------------------------------ heartbeat */

static void test_heartbeat(void)
{
    vx_heartbeat_t hb;
    vx_hb_init(&hb);
    assert(!vx_hb_expired(&hb, 1000u)); /* not watching */

    vx_hb_start(&hb, 1000u);
    assert(!vx_hb_expired(&hb, 1000u + VP_HEARTBEAT_TIMEOUT_MS));
    assert(vx_hb_expired(&hb, 1001u + VP_HEARTBEAT_TIMEOUT_MS));
    vx_hb_feed(&hb, 1300u);
    assert(!vx_hb_expired(&hb, 1400u));
    vx_hb_stop(&hb);
    assert(!vx_hb_expired(&hb, 99999u));

    /* millisecond counter wraparound: 100 ms elapsed across the wrap */
    vx_hb_start(&hb, 0xFFFFFFCEu);
    assert(!vx_hb_expired(&hb, 0x00000032u));
    assert(vx_hb_expired(&hb, 0x00000100u));
    printf("heartbeat ok\n");
}

/* ------------------------------------------------------------ protection */

static void test_protection(void)
{
    uint16_t hi = 0u;
    uint16_t lo = 0u;
    uint16_t code = 0u;

    assert(vx_ocp_dac_code_high(150.0f) == 2979u); /* spec-anchored value */
    assert(vx_ocp_codes(150.0f, &hi, &lo));
    assert(hi == 2979u);
    assert(lo < 2048u); /* below midscale */

    /* backstop: outside 10..175 A rejected, values untouched */
    hi = 0xBEEFu;
    assert(!vx_ocp_codes(5.0f, &hi, &lo));
    assert(!vx_ocp_codes(200.0f, &hi, &lo));
    assert(hi == 0xBEEFu);

    /* OVP window 63.5..65.5 V */
    assert(vx_ovp_code(65.0f, &code));
    assert(code > 0u && code < 4096u);
    assert(!vx_ovp_code(63.0f, &code));  /* below brake target margin */
    assert(!vx_ovp_code(66.0f, &code));  /* above hardware backstop */
    printf("protection ok\n");
}

/* ------------------------------------------------------------ motor id */

static void test_motor_id(void)
{
    float r = 0.0f;
    float l = 0.0f;
    float flux = 0.0f;
    float kp = 0.0f;
    float ki = 0.0f;

    assert(vx_id_resistance(1.0f, 50.0f, &r) && APPROX(r, 0.02f, 1e-6f));
    assert(!vx_id_resistance(1.0f, 0.0f, &r));
    assert(vx_id_inductance(0.001f, 0.02f, &l) && APPROX(l, 2e-5f, 1e-9f));
    assert(!vx_id_inductance(0.0f, 0.02f, &l));
    assert(vx_id_flux(10.0f, 2000.0f, &flux) && APPROX(flux, 0.005f, 1e-6f));
    assert(!vx_id_flux(10.0f, 0.0f, &flux));

    /* protocol.yaml default gains from default R/L/bandwidth */
    vx_iloop_gains(0.02f, 2e-5f, 2666.667f, &kp, &ki);
    assert(APPROX(kp, 0.3351f, 5e-4f));
    assert(APPROX(ki, 335.1f, 0.5f));
    printf("motor_id ok\n");
}

/* ------------------------------------------------------------ param store */

static void test_param_store(void)
{
    vx_params_t p;
    float v = 0.0f;
    uint8_t buf[4];
    uint8_t blob[VX_PARAM_NV_MAX_SIZE];
    size_t n;
    vx_params_t q;
    int32_t idx;

    vx_params_defaults(&p);
    assert(vx_param_read(&p, 0x0001u, &v) == VP_STATUS_OK && v == 7.0f);
    assert(vx_param_read(&p, 0x9999u, &v) == VP_STATUS_NACK_BAD_PARAM);

    assert(vx_param_write(&p, 0x0001u, 14.0f) == VP_STATUS_OK);
    assert(vx_param_write(&p, 0x0001u, 65.0f) == VP_STATUS_NACK_OUT_OF_BOUNDS);
    assert(vx_param_write(&p, 0x0001u, 0.0f) == VP_STATUS_NACK_OUT_OF_BOUNDS);
    assert(vx_param_write(&p, 0x9999u, 1.0f) == VP_STATUS_NACK_BAD_PARAM);

    /* wire round-trips per type */
    idx = vx_param_index(0x0002u); /* f32 */
    assert(vx_param_encode_value(&VP_PARAMS[idx], 0.0187f, buf) == 4u);
    assert(vx_param_decode_value(&VP_PARAMS[idx], buf, 4u, &v));
    assert(APPROX(v, 0.0187f, 1e-7f));
    assert(!vx_param_decode_value(&VP_PARAMS[idx], buf, 2u, &v));

    idx = vx_param_index(0x0001u); /* u8 */
    assert(vx_param_encode_value(&VP_PARAMS[idx], 7.0f, buf) == 1u);
    assert(buf[0] == 7u);
    idx = vx_param_index(0x0502u); /* u16 */
    assert(vx_param_encode_value(&VP_PARAMS[idx], 258.0f, buf) == 2u);
    assert(buf[0] == 2u && buf[1] == 1u);
    idx = vx_param_index(0x0311u); /* i32 */
    assert(vx_param_encode_value(&VP_PARAMS[idx], 4096.0f, buf) == 4u);
    assert(vx_param_decode_value(&VP_PARAMS[idx], buf, 4u, &v) && v == 4096.0f);

    /* NV blob round-trip */
    (void)vx_param_write(&p, 0x0002u, 0.5f);
    n = vx_params_nv_serialize(&p, blob, sizeof blob);
    assert(n > 8u);
    vx_params_defaults(&q);
    assert(vx_params_nv_deserialize(&q, blob, n));
    assert(vx_param_read(&q, 0x0001u, &v) == VP_STATUS_OK && v == 14.0f);
    assert(vx_param_read(&q, 0x0002u, &v) == VP_STATUS_OK && APPROX(v, 0.5f, 1e-7f));

    /* corruption rejected, target untouched */
    blob[10] ^= 0xFFu;
    vx_params_defaults(&q);
    assert(!vx_params_nv_deserialize(&q, blob, n));
    assert(vx_param_read(&q, 0x0001u, &v) == VP_STATUS_OK && v == 7.0f);
    assert(!vx_params_nv_deserialize(&q, blob, 4u));
    printf("param_store ok\n");
}

/* ------------------------------------------------------------ nv store */

#define MOCK_SLOT_SIZE 512u
typedef struct {
    uint8_t mem[2][MOCK_SLOT_SIZE];
    int erase_count[2];
    bool fail_write;
} mock_flash_t;

static bool mock_erase(void *ctx, uint8_t slot)
{
    mock_flash_t *m = ctx;
    memset(m->mem[slot], 0xFF, MOCK_SLOT_SIZE);
    m->erase_count[slot]++;
    return true;
}

static bool mock_write(void *ctx, uint8_t slot, uint32_t off,
                       const uint8_t *data, size_t len)
{
    mock_flash_t *m = ctx;
    if (m->fail_write) {
        return false;
    }
    memcpy(&m->mem[slot][off], data, len);
    return true;
}

static bool mock_read(void *ctx, uint8_t slot, uint32_t off, uint8_t *data,
                      size_t len)
{
    mock_flash_t *m = ctx;
    memcpy(data, &m->mem[slot][off], len);
    return true;
}

static void test_nv_store(void)
{
    mock_flash_t flash;
    vx_nv_ops_t ops = { mock_erase, mock_write, mock_read, MOCK_SLOT_SIZE, &flash };
    uint8_t out[64];
    uint8_t rec1[] = "record-one";
    uint8_t rec2[] = "record-two!";
    uint8_t rec3[] = "record-three";

    memset(&flash, 0xFF, sizeof flash);
    flash.erase_count[0] = flash.erase_count[1] = 0;
    flash.fail_write = false;

    assert(vx_nv_load(&ops, out, sizeof out) == -1); /* virgin flash */

    assert(vx_nv_save(&ops, rec1, sizeof rec1));
    assert(vx_nv_load(&ops, out, sizeof out) == (int32_t)sizeof rec1);
    assert(memcmp(out, rec1, sizeof rec1) == 0);

    /* ping-pong: second save goes to the other slot */
    assert(vx_nv_save(&ops, rec2, sizeof rec2));
    assert(flash.erase_count[0] == 1 && flash.erase_count[1] == 1);
    assert(vx_nv_load(&ops, out, sizeof out) == (int32_t)sizeof rec2);
    assert(memcmp(out, rec2, sizeof rec2) == 0);

    assert(vx_nv_save(&ops, rec3, sizeof rec3));
    assert(vx_nv_load(&ops, out, sizeof out) == (int32_t)sizeof rec3);

    /* corrupt the newest record -> falls back to the previous one */
    {
        uint8_t slot = (memcmp(&flash.mem[0][VX_NV_HEADER_SIZE], rec3,
                               sizeof rec3) == 0) ? 0u : 1u;
        flash.mem[slot][VX_NV_HEADER_SIZE] ^= 0xFFu;
        assert(vx_nv_load(&ops, out, sizeof out) == (int32_t)sizeof rec2);
        assert(memcmp(out, rec2, sizeof rec2) == 0);
    }

    /* oversized record rejected */
    {
        uint8_t big[MOCK_SLOT_SIZE];
        memset(big, 0, sizeof big);
        assert(!vx_nv_save(&ops, big, (uint16_t)sizeof big));
    }
    printf("nv_store ok\n");
}

/* ------------------------------------------------------------ telemetry */

static void test_telemetry(void)
{
    vx_telem_t t;
    int16_t raw[3] = { 100, -200, 300 };
    const uint8_t *pl;
    uint16_t len = 0u;

    assert(vx_popcount32(0u) == 0u);
    assert(vx_popcount32(0x80000001u) == 2u);

    assert(vx_telem_encode(1.0f, 0.01f) == 100);
    assert(vx_telem_encode(-1.0f, 0.01f) == -100);
    assert(vx_telem_encode(1e6f, 0.01f) == 32767);   /* clamped */
    assert(vx_telem_encode(-1e6f, 0.01f) == -32768);

    vx_telem_begin(&t, 0x11223344u, 0x7u, 8u); /* ia|ib|ic */
    assert(t.nch == 3u);
    assert(vx_telem_add(&t, 0u, raw));
    assert(vx_telem_add(&t, 200u, raw));
    pl = vx_telem_payload(&t, &len);
    assert(len == 12u + 2u * (2u + 6u));
    /* header layout */
    assert(pl[0] == 0x44u && pl[1] == 0x33u && pl[2] == 0x22u && pl[3] == 0x11u);
    assert(pl[4] == 0x07u && pl[5] == 0u && pl[6] == 0u && pl[7] == 0u);
    assert(pl[8] == 2u && pl[9] == 0u);              /* n_samples */
    assert(pl[10] == 8u && pl[11] == 0u);            /* decimation */
    /* first sample: t_off=0, ia=100 LE */
    assert(pl[12] == 0u && pl[13] == 0u);
    assert(pl[14] == 100u && pl[15] == 0u);
    /* ib=-200 LE two's complement */
    assert(pl[16] == (uint8_t)(-200 & 0xFF) && pl[17] == (uint8_t)((-200 >> 8) & 0xFF));

    /* capacity: fill until add refuses; must match vx_telem_max_samples */
    {
        uint16_t max = vx_telem_max_samples(0x7u);
        uint16_t added = 2u;
        while (vx_telem_add(&t, (uint16_t)(added * 200u), raw)) {
            added++;
        }
        assert(added == max);
        pl = vx_telem_payload(&t, &len);
        assert(len <= VP_MAX_PAYLOAD);
    }
    printf("telemetry ok\n");
}

/* ------------------------------------------------------------ usb tx */

static void test_usb_tx(void)
{
    uint8_t storage[256];
    vx_usb_tx_t tx;
    uint8_t frame[100];
    uint8_t pkt[VX_USB_PKT_SIZE];
    uint16_t len = 0u;

    assert(vx_usb_tx_init(&tx, storage, sizeof storage));
    assert(!vx_usb_tx_next(&tx, pkt, &len)); /* idle: nothing to send */

    memset(frame, 0x5A, sizeof frame);
    assert(vx_usb_tx_queue(&tx, frame, 100u));
    assert(vx_usb_tx_next(&tx, pkt, &len) && len == 64u);
    assert(vx_usb_tx_next(&tx, pkt, &len) && len == 36u);
    assert(!vx_usb_tx_next(&tx, pkt, &len)); /* short final packet: no ZLP */

    /* exactly 128 bytes -> two full packets then a ZLP */
    assert(vx_usb_tx_queue(&tx, frame, 100u));
    assert(vx_usb_tx_queue(&tx, frame, 28u));
    assert(vx_usb_tx_next(&tx, pkt, &len) && len == 64u);
    assert(vx_usb_tx_next(&tx, pkt, &len) && len == 64u);
    assert(vx_usb_tx_next(&tx, pkt, &len) && len == 0u); /* ZLP */
    assert(!vx_usb_tx_next(&tx, pkt, &len));

    /* all-or-nothing queue: 255-byte ring refuses the third 100B frame */
    assert(vx_usb_tx_queue(&tx, frame, 100u));
    assert(vx_usb_tx_queue(&tx, frame, 100u));
    assert(!vx_usb_tx_queue(&tx, frame, 100u));
    printf("usb_tx ok\n");
}

/* ------------------------------------------------------------ device */

typedef struct {
    vx_device_t dev;
    vp_decoder_t dec;
    uint8_t seq;
} harness_t;

/* Send one command, return the response payload (status at [0]) or NULL. */
static const uint8_t *xfer(harness_t *h, uint8_t cmd, const uint8_t *payload,
                           uint16_t len, uint16_t *rlen, uint32_t now_ms)
{
    static uint8_t rx_payload[VP_MAX_PAYLOAD];
    uint8_t wire[VP_MAX_WIRE];
    uint8_t resp[VP_MAX_WIRE];
    vp_frame_t f;
    vp_frame_t rf;
    int32_t wn;
    int32_t rn;
    int32_t i;
    int got = 0;

    h->seq++;
    wn = vp_encode_wire(wire, sizeof wire, cmd, h->seq, 0u, payload, len);
    assert(wn > 0);
    /* decode what we sent to get a vp_frame_t view (host->device path) */
    for (i = 0; i < wn; i++) {
        got = vp_decoder_feed(&h->dec, wire[i], &f);
    }
    assert(got == 1);
    rn = vx_device_handle_frame(&h->dev, &f, now_ms, resp, sizeof resp);
    if (rn == 0) {
        return NULL;
    }
    got = 0;
    for (i = 0; i < rn; i++) {
        got = vp_decoder_feed(&h->dec, resp[i], &rf);
    }
    assert(got == 1);
    assert(rf.cmd == cmd);
    assert(rf.seq == h->seq);
    assert((rf.flags & VP_FLAG_RESPONSE) != 0u);
    memcpy(rx_payload, rf.payload, rf.len);
    *rlen = rf.len;
    return rx_payload;
}

static void test_device(void)
{
    harness_t h;
    const uint8_t *r;
    uint16_t rlen = 0u;
    uint8_t pl[16];
    mock_flash_t flash;
    vx_nv_ops_t ops = { mock_erase, mock_write, mock_read, MOCK_SLOT_SIZE, &flash };

    memset(&flash, 0xFF, sizeof flash);
    flash.erase_count[0] = flash.erase_count[1] = 0;
    flash.fail_write = false;

    vp_decoder_init(&h.dec);
    h.seq = 0u;
    vx_device_init(&h.dev, &ops);
    assert(h.dev.state == VP_DEVICE_STATE_INIT);
    vx_device_ready(&h.dev);
    assert(h.dev.state == VP_DEVICE_STATE_STANDBY);

    /* HELLO */
    r = xfer(&h, VP_CMD_HELLO, NULL, 0u, &rlen, 0u);
    assert(r && r[0] == VP_STATUS_OK && rlen == 3u);
    assert(r[1] == VP_PROTOCOL_VERSION_MAJOR && r[2] == VP_PROTOCOL_VERSION_MINOR);

    /* DEVICE_INFO: fw + uid + name */
    r = xfer(&h, VP_CMD_DEVICE_INFO, NULL, 0u, &rlen, 0u);
    assert(r && r[0] == VP_STATUS_OK);
    assert(rlen == 1u + 3u + VX_UID_LEN + (uint16_t)strlen(VX_DEVICE_NAME));

    /* PARAM_LIST count */
    r = xfer(&h, VP_CMD_PARAM_LIST, NULL, 0u, &rlen, 0u);
    assert(r && r[0] == VP_STATUS_OK);
    assert(r[1] == VP_PARAM_COUNT && r[2] == 0u);
    assert(rlen == 3u + (VP_PARAM_COUNT * 2u));

    /* PARAM_READ pole_pairs default 7 (u8) */
    pl[0] = 0x01u; pl[1] = 0x00u;
    r = xfer(&h, VP_CMD_PARAM_READ, pl, 2u, &rlen, 0u);
    assert(r && r[0] == VP_STATUS_OK && rlen == 4u && r[3] == 7u);

    /* PARAM_WRITE ok, then out-of-bounds, then unknown, then bad length */
    pl[0] = 0x01u; pl[1] = 0x00u; pl[2] = 14u;
    r = xfer(&h, VP_CMD_PARAM_WRITE, pl, 3u, &rlen, 0u);
    assert(r && r[0] == VP_STATUS_OK);
    pl[2] = 65u;
    r = xfer(&h, VP_CMD_PARAM_WRITE, pl, 3u, &rlen, 0u);
    assert(r && r[0] == VP_STATUS_NACK_OUT_OF_BOUNDS);
    pl[0] = 0x99u; pl[1] = 0x99u; pl[2] = 1u;
    r = xfer(&h, VP_CMD_PARAM_WRITE, pl, 3u, &rlen, 0u);
    assert(r && r[0] == VP_STATUS_NACK_BAD_PARAM);
    pl[0] = 0x01u; pl[1] = 0x00u; pl[2] = 7u; pl[3] = 0u;
    r = xfer(&h, VP_CMD_PARAM_WRITE, pl, 4u, &rlen, 0u);
    assert(r && r[0] == VP_STATUS_NACK_BAD_LEN);

    /* ARM -> heartbeat keeps alive -> timeout trips HEARTBEAT_LOSS */
    r = xfer(&h, VP_CMD_ARM, NULL, 0u, &rlen, 1000u);
    assert(r && r[0] == VP_STATUS_OK);
    assert(h.dev.state == VP_DEVICE_STATE_ARMED);

    /* param write while armed -> BAD_STATE */
    pl[0] = 0x01u; pl[1] = 0x00u; pl[2] = 7u;
    r = xfer(&h, VP_CMD_PARAM_WRITE, pl, 3u, &rlen, 1010u);
    assert(r && r[0] == VP_STATUS_NACK_BAD_STATE);

    r = xfer(&h, VP_CMD_HEARTBEAT, NULL, 0u, &rlen, 1050u);
    assert(r && r[0] == VP_STATUS_OK && rlen == 6u);
    assert(r[1] == (uint8_t)VP_DEVICE_STATE_ARMED);

    vx_device_tick(&h.dev, 1200u); /* 150 ms since feed: fine */
    assert(h.dev.state == VP_DEVICE_STATE_ARMED);
    vx_device_tick(&h.dev, 1300u); /* 250 ms: expired */
    assert(h.dev.state == VP_DEVICE_STATE_FAULT);
    assert((h.dev.fault_latched & VP_FAULT_HEARTBEAT_LOSS) != 0u);
    assert(h.dev.fault_active == 0u); /* transient: condition not active */

    /* FAULT_CLEAR returns to STANDBY */
    r = xfer(&h, VP_CMD_FAULT_CLEAR, NULL, 0u, &rlen, 1400u);
    assert(r && r[0] == VP_STATUS_OK);
    assert(h.dev.state == VP_DEVICE_STATE_STANDBY);

    /* SETPOINT drives ARMED <-> RUNNING; STOP always honored */
    r = xfer(&h, VP_CMD_ARM, NULL, 0u, &rlen, 2000u);
    assert(r && r[0] == VP_STATUS_OK);
    pl[0] = (uint8_t)VP_SETPOINT_MODE_TORQUE;
    pl[1] = 0u; pl[2] = 0u; pl[3] = 0x20u; pl[4] = 0x41u; /* 10.0f LE */
    r = xfer(&h, VP_CMD_SETPOINT, pl, 5u, &rlen, 2010u);
    assert(r && r[0] == VP_STATUS_OK);
    assert(h.dev.state == VP_DEVICE_STATE_RUNNING);
    r = xfer(&h, VP_CMD_STOP, NULL, 0u, &rlen, 2020u);
    assert(r && r[0] == VP_STATUS_OK);
    assert(h.dev.state == VP_DEVICE_STATE_STANDBY);
    assert(h.dev.setpoint == 0.0f);

    /* SETPOINT in STANDBY -> BAD_STATE */
    r = xfer(&h, VP_CMD_SETPOINT, pl, 5u, &rlen, 2030u);
    assert(r && r[0] == VP_STATUS_NACK_BAD_STATE);

    /* hardware fault: FAULT_CLEAR refused while condition active */
    vx_device_fault_set(&h.dev, VP_FAULT_OVERCURRENT_BIT);
    assert(h.dev.state == VP_DEVICE_STATE_FAULT);
    r = xfer(&h, VP_CMD_FAULT_CLEAR, NULL, 0u, &rlen, 2100u);
    assert(r && r[0] == VP_STATUS_NACK_BAD_STATE);
    r = xfer(&h, VP_CMD_FAULT_READ, NULL, 0u, &rlen, 2100u);
    assert(r && r[0] == VP_STATUS_OK);
    assert((r[1] & (uint8_t)VP_FAULT_OVERCURRENT) != 0u);
    vx_device_fault_clear_condition(&h.dev, VP_FAULT_OVERCURRENT_BIT);
    r = xfer(&h, VP_CMD_FAULT_CLEAR, NULL, 0u, &rlen, 2110u);
    assert(r && r[0] == VP_STATUS_OK);
    assert(h.dev.state == VP_DEVICE_STATE_STANDBY);

    /* PROTECTION_SET: valid updates DAC codes, invalid rejected atomically */
    {
        uint8_t pp[8];
        float oc = 120.0f;
        float ov = 64.0f;
        uint16_t prev_hi;
        memcpy(&pp[0], &oc, 4u);
        memcpy(&pp[4], &ov, 4u);
        r = xfer(&h, VP_CMD_PROTECTION_SET, pp, 8u, &rlen, 2200u);
        assert(r && r[0] == VP_STATUS_OK);
        prev_hi = h.dev.ocp_code_high;
        assert(prev_hi == vx_ocp_dac_code_high(120.0f));
        ov = 70.0f; /* above backstop window */
        memcpy(&pp[4], &ov, 4u);
        r = xfer(&h, VP_CMD_PROTECTION_SET, pp, 8u, &rlen, 2210u);
        assert(r && r[0] == VP_STATUS_NACK_OUT_OF_BOUNDS);
        assert(h.dev.ocp_code_high == prev_hi);
    }

    /* MOTOR_ID: STANDBY only, BUSY while running, results land in params */
    r = xfer(&h, VP_CMD_MOTOR_ID_START, NULL, 0u, &rlen, 2300u);
    assert(r && r[0] == VP_STATUS_OK);
    r = xfer(&h, VP_CMD_MOTOR_ID_START, NULL, 0u, &rlen, 2310u);
    assert(r && r[0] == VP_STATUS_BUSY);
    r = xfer(&h, VP_CMD_ARM, NULL, 0u, &rlen, 2320u);
    assert(r && r[0] == VP_STATUS_BUSY);
    vx_device_motor_id_finish(&h.dev, 0.0187f, 1.55e-5f, 1.62e-5f, 0.0048f);
    pl[0] = 0x02u; pl[1] = 0x00u; /* motor.r_phase */
    r = xfer(&h, VP_CMD_PARAM_READ, pl, 2u, &rlen, 2330u);
    assert(r && r[0] == VP_STATUS_OK);
    {
        float rv;
        memcpy(&rv, &r[3], 4u);
        assert(APPROX(rv, 0.0187f, 1e-6f));
    }

    /* TELEMETRY_START/STOP config; mask 0 rejected */
    pl[0] = 0x07u; pl[1] = 0u; pl[2] = 0u; pl[3] = 0u; pl[4] = 8u; pl[5] = 0u;
    r = xfer(&h, VP_CMD_TELEMETRY_START, pl, 6u, &rlen, 2400u);
    assert(r && r[0] == VP_STATUS_OK);
    assert(h.dev.telem_on && h.dev.telem_mask == 7u && h.dev.telem_decimation == 8u);
    memset(pl, 0, 6u);
    pl[4] = 8u;
    r = xfer(&h, VP_CMD_TELEMETRY_START, pl, 6u, &rlen, 2405u);
    assert(r && r[0] == VP_STATUS_NACK_OUT_OF_BOUNDS);
    r = xfer(&h, VP_CMD_TELEMETRY_STOP, NULL, 0u, &rlen, 2410u);
    assert(r && r[0] == VP_STATUS_OK && !h.dev.telem_on);

    /* PARAM_SAVE -> defaults -> PARAM_LOAD restores */
    pl[0] = 0x01u; pl[1] = 0x00u; pl[2] = 21u;
    r = xfer(&h, VP_CMD_PARAM_WRITE, pl, 3u, &rlen, 2500u);
    assert(r && r[0] == VP_STATUS_OK);
    r = xfer(&h, VP_CMD_PARAM_SAVE, NULL, 0u, &rlen, 2510u);
    assert(r && r[0] == VP_STATUS_OK);
    r = xfer(&h, VP_CMD_PARAM_DEFAULT, NULL, 0u, &rlen, 2520u);
    assert(r && r[0] == VP_STATUS_OK);
    pl[0] = 0x01u; pl[1] = 0x00u;
    r = xfer(&h, VP_CMD_PARAM_READ, pl, 2u, &rlen, 2530u);
    assert(r && r[3] == 7u);
    r = xfer(&h, VP_CMD_PARAM_LOAD, NULL, 0u, &rlen, 2540u);
    assert(r && r[0] == VP_STATUS_OK);
    r = xfer(&h, VP_CMD_PARAM_READ, pl, 2u, &rlen, 2550u);
    assert(r && r[3] == 21u);

    /* NV round-trip across reboot: fresh device instance sees saved params */
    {
        vx_device_t d2;
        float v = 0.0f;
        vx_device_init(&d2, &ops);
        assert(vx_param_read(&d2.params, 0x0001u, &v) == VP_STATUS_OK);
        assert(v == 21.0f);
    }

    /* SCOPE: config -> arm -> capture install -> chunked read */
    {
        uint8_t sc[12];
        static uint8_t capture[700];
        uint32_t i;
        memset(sc, 0, sizeof sc);
        r = xfer(&h, VP_CMD_SCOPE_READ, sc, 4u, &rlen, 2600u);
        assert(r && r[0] == VP_STATUS_NACK_BAD_STATE); /* no capture yet */
        r = xfer(&h, VP_CMD_SCOPE_ARM, NULL, 0u, &rlen, 2601u);
        assert(r && r[0] == VP_STATUS_NACK_BAD_STATE); /* not configured */
        sc[0] = 0x07u;       /* mask */
        sc[4] = 4u;          /* decimation */
        r = xfer(&h, VP_CMD_SCOPE_CONFIG, sc, 12u, &rlen, 2602u);
        assert(r && r[0] == VP_STATUS_OK);
        r = xfer(&h, VP_CMD_SCOPE_ARM, NULL, 0u, &rlen, 2603u);
        assert(r && r[0] == VP_STATUS_OK);
        assert(h.dev.scope_trigger_requested);

        for (i = 0u; i < sizeof capture; i++) {
            capture[i] = (uint8_t)i;
        }
        vx_device_set_scope_capture(&h.dev, capture, sizeof capture);

        memset(sc, 0, 4u);
        r = xfer(&h, VP_CMD_SCOPE_READ, sc, 4u, &rlen, 2604u);
        assert(r && r[0] == VP_STATUS_OK);
        {
            uint32_t total = (uint32_t)r[1] | ((uint32_t)r[2] << 8) |
                             ((uint32_t)r[3] << 16) | ((uint32_t)r[4] << 24);
            uint32_t chunk = (uint32_t)rlen - 9u;
            assert(total == sizeof capture);
            assert(chunk == VP_MAX_PAYLOAD - 9u);
            sc[0] = (uint8_t)(chunk & 0xFFu);
            sc[1] = (uint8_t)(chunk >> 8);
            sc[2] = 0u; sc[3] = 0u;
            r = xfer(&h, VP_CMD_SCOPE_READ, sc, 4u, &rlen, 2605u);
            assert(r && r[0] == VP_STATUS_OK);
            assert(((uint32_t)rlen - 9u) == (sizeof capture - chunk));
            assert(r[9] == capture[chunk]);
        }
    }

    /* REBOOT/DFU set pending action after OK reply */
    r = xfer(&h, VP_CMD_ENTER_DFU, NULL, 0u, &rlen, 2700u);
    assert(r && r[0] == VP_STATUS_OK);
    assert(h.dev.pending == VX_ACTION_ENTER_DFU);

    /* unknown command NACKed */
    r = xfer(&h, 0x6Fu, NULL, 0u, &rlen, 2800u);
    assert(r && r[0] == VP_STATUS_NACK_UNKNOWN_CMD);

    printf("device ok\n");
}

int main(void)
{
    test_spsc();
    test_heartbeat();
    test_protection();
    test_motor_id();
    test_param_store();
    test_nv_store();
    test_telemetry();
    test_usb_tx();
    test_device();
    printf("all FW-VECTOR-01B App tests passed\n");
    return 0;
}
