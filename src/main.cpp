#include <Arduino.h>
#include <Adafruit_TinyUSB.h>
#include "ssd1309.h"
#include "protocol.h"

// ---- Pin configuration (RP2350-Zero, SPI0) ----
#ifndef OLED_PIN_SCK
#define OLED_PIN_SCK 2   // SPI0 SCK  -> OLED D0/SCL/CLK
#endif
#ifndef OLED_PIN_MOSI
#define OLED_PIN_MOSI 3  // SPI0 TX   -> OLED D1/SDA/DIN
#endif
#ifndef OLED_PIN_CS
#define OLED_PIN_CS 5    // -> OLED CS
#endif
#ifndef OLED_PIN_DC
#define OLED_PIN_DC 6    // -> OLED DC
#endif
#ifndef OLED_PIN_RST
#define OLED_PIN_RST 7   // -> OLED RES
#endif
#ifndef OLED_SPI_HZ
#define OLED_SPI_HZ 8000000
#endif

#ifndef PICOLED_USB_VID
#define PICOLED_USB_VID 0x1209
#endif
#ifndef PICOLED_USB_PID
#define PICOLED_USB_PID 0x0001
#endif

#define PARSER_TIMEOUT_MS 500

static SSD1309 oled(OLED_PIN_SCK, OLED_PIN_MOSI, OLED_PIN_CS, OLED_PIN_DC, OLED_PIN_RST, OLED_SPI_HZ);

// Vendor-class interface with one bulk OUT + one bulk IN endpoint.
// WebUSB class is used because it also provides MS OS 2.0 descriptors so
// Windows binds WinUSB automatically (no driver install needed).
static Adafruit_USBD_WebUSB vendor;

static uint8_t rxBuf[PICOLED_MAX_PAYLOAD];
static uint8_t hdr[4];
static size_t hdrPos = 0;
static size_t payloadLen = 0;
static size_t payloadPos = 0;
static uint32_t lastByteMs = 0;

static void sendResponse(uint8_t cmd, uint8_t status, const uint8_t *payload = nullptr, uint8_t len = 0) {
    uint8_t out[4 + 32];
    out[0] = PICOLED_RSP_MAGIC;
    out[1] = cmd;
    out[2] = status;
    out[3] = len;
    if (len) memcpy(out + 4, payload, len);
    // Bypass Adafruit_USBD_WebUSB::write(), which drops data unless the host
    // performed the WebSerial "connect" control request.
    size_t total = 4 + len, sent = 0;
    uint32_t start = millis();
    while (sent < total && tud_vendor_mounted() && millis() - start < 100) {
        sent += tud_vendor_write(out + sent, total - sent);
        tud_vendor_flush();
        if (sent < total) yield();
    }
}

static uint8_t handle(uint8_t cmd, const uint8_t *p, size_t n) {
    switch (cmd) {
    case CMD_PING: {
        const uint8_t info[] = {'P', 'I', 'C', 'O', 'L', 'E', 'D',
                                PICOLED_VERSION_MAJOR, PICOLED_VERSION_MINOR,
                                SSD1309::WIDTH, SSD1309::HEIGHT};
        sendResponse(cmd, ST_OK, info, sizeof(info));
        return 0xFF; // response already sent
    }
    case CMD_INIT:
        oled.reset();
        oled.init();
        return ST_OK;
    case CMD_FILL:
        if (n != 1) return ST_BAD_LENGTH;
        oled.fill(p[0]);
        return ST_OK;
    case CMD_FRAME:
        if (n != SSD1309::FB_SIZE) return ST_BAD_LENGTH;
        oled.writeFrame(p);
        return ST_OK;
    case CMD_REGION: {
        if (n < 4) return ST_BAD_LENGTH;
        uint8_t x = p[0], page = p[1], w = p[2], pages = p[3];
        if (w == 0 || pages == 0 || x + w > SSD1309::WIDTH || page + pages > SSD1309::PAGES) return ST_BAD_ARG;
        if (n != 4 + (size_t)w * pages) return ST_BAD_LENGTH;
        oled.writeRegion(x, page, w, pages, p + 4);
        return ST_OK;
    }
    case CMD_CONTRAST:
        if (n != 1) return ST_BAD_LENGTH;
        oled.setContrast(p[0]);
        return ST_OK;
    case CMD_INVERT:
        if (n != 1) return ST_BAD_LENGTH;
        oled.setInvert(p[0]);
        return ST_OK;
    case CMD_POWER:
        if (n != 1) return ST_BAD_LENGTH;
        oled.setPower(p[0]);
        return ST_OK;
    case CMD_FLIP:
        if (n != 1) return ST_BAD_LENGTH;
        oled.setFlip(p[0]);
        return ST_OK;
    case CMD_RAW:
        if (n == 0) return ST_BAD_LENGTH;
        oled.commands(p, n);
        return ST_OK;
    default:
        return ST_BAD_CMD;
    }
}

static void resetParser() {
    hdrPos = 0;
    payloadLen = 0;
    payloadPos = 0;
}

static void dispatch() {
    uint8_t cmd = hdr[1];
    uint8_t st = handle(cmd, rxBuf, payloadLen);
    if (st != 0xFF) sendResponse(cmd, st);
    resetParser();
}

static void pollUsb() {
    if ((hdrPos || payloadPos) && millis() - lastByteMs > PARSER_TIMEOUT_MS) resetParser();

    while (vendor.available()) {
        lastByteMs = millis();

        if (hdrPos < sizeof(hdr)) {
            int c = vendor.read();
            if (c < 0) break;
            if (hdrPos == 0 && c != PICOLED_REQ_MAGIC) continue; // resync
            hdr[hdrPos++] = (uint8_t)c;
            if (hdrPos == sizeof(hdr)) {
                payloadLen = hdr[2] | (hdr[3] << 8);
                payloadPos = 0;
                if (payloadLen > sizeof(rxBuf)) {
                    sendResponse(hdr[1], ST_BAD_LENGTH);
                    resetParser();
                    continue;
                }
                if (payloadLen == 0) dispatch();
            }
            continue;
        }

        uint32_t got = vendor.read(rxBuf + payloadPos, payloadLen - payloadPos);
        if (got == 0) break;
        payloadPos += got;
        if (payloadPos == payloadLen) dispatch();
    }
}

static void drawSplash() {
    static uint8_t fb[SSD1309::FB_SIZE];
    memset(fb, 0, sizeof(fb));
    for (int x = 0; x < SSD1309::WIDTH; x++) {
        fb[x] |= 0x01;                                    // top line
        fb[(SSD1309::PAGES - 1) * SSD1309::WIDTH + x] |= 0x80; // bottom line
    }
    for (int p = 0; p < SSD1309::PAGES; p++) {
        fb[p * SSD1309::WIDTH] = 0xFF;                    // left line
        fb[p * SSD1309::WIDTH + SSD1309::WIDTH - 1] = 0xFF; // right line
    }
    oled.writeFrame(fb);
}

void setup() {
    if (!TinyUSBDevice.isInitialized()) TinyUSBDevice.begin(0);

    TinyUSBDevice.setID(PICOLED_USB_VID, PICOLED_USB_PID);
    TinyUSBDevice.setManufacturerDescriptor("picoled");
    TinyUSBDevice.setProductDescriptor("PicoLED SSD1309");

    vendor.setStringDescriptor("PicoLED bulk");
    vendor.begin();

    // Re-enumerate so the host sees the vendor interface added after core init.
    if (TinyUSBDevice.mounted()) {
        TinyUSBDevice.detach();
        delay(10);
        TinyUSBDevice.attach();
    }

    Serial.begin(115200);

    oled.begin();
    drawSplash();
}

void loop() {
#ifdef TINYUSB_NEED_POLLING_TASK
    TinyUSBDevice.task();
#endif
    pollUsb();
}
