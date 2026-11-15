#pragma once
#include <Arduino.h>

// Minimal SSD1309 (128x64) driver over 4-wire SPI.
// Framebuffer format: 8 pages x 128 columns, 1 byte per column per page,
// bit0 = top pixel of the page (native SSD130x page layout).
class SSD1309 {
public:
    static constexpr uint8_t WIDTH = 128;
    static constexpr uint8_t HEIGHT = 64;
    static constexpr uint8_t PAGES = HEIGHT / 8;
    static constexpr size_t FB_SIZE = WIDTH * PAGES;

    SSD1309(uint8_t pinSck, uint8_t pinMosi, uint8_t pinCs, uint8_t pinDc, uint8_t pinRst, uint32_t spiHz);

    void begin();
    void reset();
    void init();

    void command(uint8_t c);
    void commands(const uint8_t *buf, size_t len);
    void data(const uint8_t *buf, size_t len);

    // Write a rectangular block of pages. data is w*pages bytes, row (page) major.
    void writeRegion(uint8_t x, uint8_t page, uint8_t w, uint8_t pages, const uint8_t *buf);
    void writeFrame(const uint8_t *buf) { writeRegion(0, 0, WIDTH, PAGES, buf); }
    void fill(uint8_t pattern);

    void setContrast(uint8_t v);
    void setInvert(bool inv);
    void setPower(bool on);
    void setFlip(bool flip180);

private:
    void beginTx(bool isData);
    void endTx();

    uint8_t _sck, _mosi, _cs, _dc, _rst;
    uint32_t _hz;
};
