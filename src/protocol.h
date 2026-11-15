#pragma once
// Shared USB protocol definition (mirrored in host/picoled.py).
//
// Request  (host -> device, bulk OUT): [0xA5][cmd][len_lo][len_hi][payload: len bytes]
// Response (device -> host, bulk IN):  [0x5A][cmd][status][len][payload: len bytes]
// Every request gets exactly one response.

#define PICOLED_VERSION_MAJOR 1
#define PICOLED_VERSION_MINOR 0

#define PICOLED_REQ_MAGIC 0xA5
#define PICOLED_RSP_MAGIC 0x5A

enum PicoledCmd : uint8_t {
    CMD_PING     = 0x00, // -> "PICOLED", ver_major, ver_minor, width, height
    CMD_INIT     = 0x01, // hardware reset + init sequence
    CMD_FILL     = 0x02, // [pattern]
    CMD_FRAME    = 0x03, // [1024 bytes framebuffer]
    CMD_REGION   = 0x04, // [x, page, w, pages, data(w*pages)]
    CMD_CONTRAST = 0x05, // [value]
    CMD_INVERT   = 0x06, // [0|1]
    CMD_POWER    = 0x07, // [0|1]
    CMD_FLIP     = 0x08, // [0|1] rotate 180 degrees
    CMD_RAW      = 0x09, // [command bytes...] sent with D/C low
};

enum PicoledStatus : uint8_t {
    ST_OK          = 0x00,
    ST_BAD_CMD     = 0x01,
    ST_BAD_LENGTH  = 0x02,
    ST_BAD_ARG     = 0x03,
};

#define PICOLED_MAX_PAYLOAD (4 + 128 * 8)
