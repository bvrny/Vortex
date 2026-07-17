/*
 * Host-compilable tests for the generated C protocol header.
 * Build: gcc -std=c11 -Wall -Wextra -Werror -I../../generated test_protocol.c -o test_protocol
 * Exit code 0 = all pass.
 */
#include <stdio.h>
#include <stdlib.h>

#include "vortex_protocol.h"

static int g_failures = 0;

#define CHECK(cond)                                                        \
    do {                                                                   \
        if (!(cond)) {                                                     \
            (void)fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #cond); \
            g_failures++;                                                  \
        }                                                                  \
    } while (0)

static void test_crc16_check_value(void)
{
    /* Standard CRC-16/CCITT-FALSE check value. */
    const uint8_t d[] = "123456789";
    CHECK(vp_crc16(d, 9u, VP_CRC_INIT) == 0x29B1u);
    CHECK(vp_crc16(d, 0u, VP_CRC_INIT) == 0xFFFFu);
}

static void test_cobs_vectors(void)
{
    /* Canonical vectors: decoded -> encoded (no trailing delimiter). */
    static const uint8_t dec1[] = {0x11, 0x22, 0x00, 0x33};
    static const uint8_t enc1[] = {0x03, 0x11, 0x22, 0x02, 0x33};
    uint8_t buf[64];
    uint8_t out[64];

    CHECK(vp_cobs_encode(buf, dec1, sizeof dec1) == sizeof enc1);
    CHECK(memcmp(buf, enc1, sizeof enc1) == 0);
    CHECK(vp_cobs_decode(out, enc1, sizeof enc1) == (int32_t)sizeof dec1);
    CHECK(memcmp(out, dec1, sizeof dec1) == 0);

    /* Malformed: truncated block must be rejected. */
    {
        static const uint8_t bad[] = {0x05, 0x11, 0x22};
        CHECK(vp_cobs_decode(out, bad, sizeof bad) == -1);
    }
    /* Malformed: embedded zero must be rejected. */
    {
        static const uint8_t bad[] = {0x02, 0x00, 0x01};
        CHECK(vp_cobs_decode(out, bad, sizeof bad) == -1);
    }
}

static void test_cobs_roundtrip_block_boundaries(void)
{
    uint8_t src[600];
    uint8_t enc[610];
    uint8_t dec[600];
    size_t sizes[] = {253u, 254u, 255u, 256u, 509u, 510u};
    size_t s;
    size_t i;
    for (i = 0u; i < sizeof src; i++) {
        src[i] = (uint8_t)((i % 255u) + 1u); /* non-zero */
    }
    for (s = 0u; s < (sizeof sizes / sizeof sizes[0]); s++) {
        size_t n = sizes[s];
        size_t elen = vp_cobs_encode(enc, src, n);
        CHECK(vp_cobs_decode(dec, enc, elen) == (int32_t)n);
        CHECK(memcmp(dec, src, n) == 0);
    }
}

static void feed_all(vp_decoder_t *d, const uint8_t *data, size_t n,
                     vp_frame_t *out, int *got)
{
    size_t i;
    *got = 0;
    for (i = 0u; i < n; i++) {
        if (vp_decoder_feed(d, data[i], out) == 1) {
            (*got)++;
        }
    }
}

static void test_frame_roundtrip(void)
{
    uint8_t payload[3] = {0xDE, 0xAD, 0x01};
    uint8_t wire[64];
    vp_decoder_t dec;
    vp_frame_t f;
    int got;
    int32_t wlen = vp_encode_wire(wire, sizeof wire, VP_CMD_SETPOINT, 0x55u, 0u,
                                  payload, 3u);
    CHECK(wlen > 0);
    vp_decoder_init(&dec);
    feed_all(&dec, wire, (size_t)wlen, &f, &got);
    CHECK(got == 1);
    CHECK(f.cmd == (uint8_t)VP_CMD_SETPOINT);
    CHECK(f.seq == 0x55u);
    CHECK(f.len == 3u);
    CHECK(memcmp(f.payload, payload, 3u) == 0);
    CHECK(f.ver == VP_PROTOCOL_VERSION_MAJOR);
}

static void test_golden_frame_from_python(void)
{
    /* Golden wire bytes produced by the generated Python module:
     * Frame(cmd=PARAM_WRITE, seq=0x2A, payload=[01 02] + f32le(0.02)).
     * Byte-for-byte agreement between the two generated codecs. */
    static const uint8_t wire[] = {
        0x03, 0xA5, 0x01, 0x04, 0x12, 0x2A, 0x06, 0x09,
        0x01, 0x02, 0x0A, 0xD7, 0xA3, 0x3C, 0x41, 0x33, 0x00,
    };
    uint8_t mywire[64];
    uint8_t payload[6] = {0x01, 0x02, 0x0A, 0xD7, 0xA3, 0x3C};
    vp_decoder_t dec;
    vp_frame_t f;
    int got;
    int32_t wlen;

    vp_decoder_init(&dec);
    feed_all(&dec, wire, sizeof wire, &f, &got);
    CHECK(got == 1);
    CHECK(f.cmd == (uint8_t)VP_CMD_PARAM_WRITE);
    CHECK(f.seq == 0x2Au);
    CHECK(f.len == 6u);
    CHECK(memcmp(f.payload, payload, 6u) == 0);

    /* And our encoder must produce the identical bytes. */
    wlen = vp_encode_wire(mywire, sizeof mywire, VP_CMD_PARAM_WRITE, 0x2Au, 0u,
                          payload, 6u);
    CHECK(wlen == (int32_t)sizeof wire);
    CHECK(memcmp(mywire, wire, sizeof wire) == 0);
}

static void test_decoder_bad_crc_counted(void)
{
    uint8_t frame[VP_MAX_FRAME];
    uint8_t wire[VP_MAX_WIRE];
    vp_decoder_t dec;
    vp_frame_t f;
    int got;
    int32_t flen = vp_encode_frame(frame, sizeof frame, VP_CMD_ARM, 3u, 0u, NULL, 0u);
    size_t wlen;
    CHECK(flen == 9);
    frame[flen - 1] ^= 0xFFu; /* corrupt CRC */
    wlen = vp_cobs_encode(wire, frame, (size_t)flen);
    wire[wlen] = 0u;
    vp_decoder_init(&dec);
    feed_all(&dec, wire, wlen + 1u, &f, &got);
    CHECK(got == 0);
    CHECK(dec.crc_errors == 1u);
}

static void test_decoder_resync_after_garbage(void)
{
    uint8_t wire[64];
    uint8_t stream[164];
    vp_decoder_t dec;
    vp_frame_t f;
    int got;
    size_t i;
    int32_t wlen = vp_encode_wire(wire, sizeof wire, VP_CMD_HEARTBEAT, 9u, 0u, NULL, 0u);
    CHECK(wlen > 0);
    for (i = 0u; i < 99u; i++) {
        stream[i] = (uint8_t)(i + 1u); /* garbage, no zeros */
    }
    stream[99] = 0u; /* delimiter closing the garbage */
    (void)memcpy(&stream[100], wire, (size_t)wlen);
    vp_decoder_init(&dec);
    feed_all(&dec, stream, 100u + (size_t)wlen, &f, &got);
    CHECK(got == 1);
    CHECK(f.seq == 9u);
}

static void test_param_table(void)
{
    size_t i;
    CHECK(VP_PARAM_COUNT == 26u);
    CHECK(VP_PARAMS[0].id == 0x0001u);
    /* Ids must be unique and metadata sane. */
    for (i = 0u; i < VP_PARAM_COUNT; i++) {
        size_t j;
        CHECK(VP_PARAMS[i].min <= VP_PARAMS[i].def_val);
        CHECK(VP_PARAMS[i].def_val <= VP_PARAMS[i].max);
        for (j = i + 1u; j < VP_PARAM_COUNT; j++) {
            CHECK(VP_PARAMS[i].id != VP_PARAMS[j].id);
        }
    }
}

static void test_hardware_constants(void)
{
    CHECK(VP_FSW_HZ == 40000u);
    CHECK(VP_CURRENT_SENSE_V_PER_A > 0.00499f && VP_CURRENT_SENSE_V_PER_A < 0.00501f);
    CHECK(VP_BRAKE_TARGET_V == 63.0f);
    CHECK(VP_BRAKE_BACKSTOP_V == 66.0f);
    CHECK(VP_VBUS_OPERATING_MAX_V == 60.0f);
    CHECK(VP_HEARTBEAT_TIMEOUT_MS == 200u);
    CHECK(VP_CHANNEL_COUNT == 18u);
}

int main(void)
{
    test_crc16_check_value();
    test_cobs_vectors();
    test_cobs_roundtrip_block_boundaries();
    test_frame_roundtrip();
    test_golden_frame_from_python();
    test_decoder_bad_crc_counted();
    test_decoder_resync_after_garbage();
    test_param_table();
    test_hardware_constants();

    if (g_failures != 0) {
        (void)fprintf(stderr, "%d check(s) FAILED\n", g_failures);
        return EXIT_FAILURE;
    }
    (void)printf("all C protocol tests passed\n");
    return EXIT_SUCCESS;
}
