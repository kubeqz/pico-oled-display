#include "ssd1309.h"
#include <SPI.h>

SSD1309::SSD1309(uint8_t pinSck, uint8_t pinMosi, uint8_t pinCs, uint8_t pinDc, uint8_t pinRst, uint32_t spiHz)
    : _sck(pinSck), _mosi(pinMosi), _cs(pinCs), _dc(pinDc), _rst(pinRst), _hz(spiHz) {}

void SSD1309::begin() {
    pinMode(_cs, OUTPUT);
    digitalWrite(_cs, HIGH);
    pinMode(_dc, OUTPUT);
    pinMode(_rst, OUTPUT);
    digitalWrite(_rst, HIGH);

    SPI.setSCK(_sck);
    SPI.setTX(_mosi);
    SPI.begin(false);

    reset();
    init();
}

void SSD1309::reset() {
    digitalWrite(_rst, HIGH);
    delay(1);
    digitalWrite(_rst, LOW);
    delay(10);
    digitalWrite(_rst, HIGH);
    delay(10);
}

void SSD1309::init() {
    static const uint8_t seq[] = {
        0xFD, 0x12,       // unlock command interface
        0xAE,             // display off
        0xD5, 0xA0,       // clock divide / oscillator freq
        0xA8, 0x3F,       // multiplex ratio = 64
        0xD3, 0x00,       // display offset
        0x40,             // start line 0
        0x20, 0x00,       // horizontal addressing mode
        0xA1,             // segment remap (col 127 -> SEG0)
        0xC8,             // COM scan direction remapped
        0xDA, 0x12,       // COM pins: alternative config
        0x81, 0x7F,       // contrast
        0xD9, 0xF1,       // pre-charge period
        0xDB, 0x34,       // VCOMH deselect level
        0xA4,             // display follows RAM
        0xA6,             // normal (not inverted)
    };
    commands(seq, sizeof(seq));
    fill(0x00);
    command(0xAF);        // display on
}

void SSD1309::beginTx(bool isData) {
    SPI.beginTransaction(SPISettings(_hz, MSBFIRST, SPI_MODE0));
    digitalWrite(_dc, isData ? HIGH : LOW);
    digitalWrite(_cs, LOW);
}

void SSD1309::endTx() {
    digitalWrite(_cs, HIGH);
    SPI.endTransaction();
}

void SSD1309::command(uint8_t c) { commands(&c, 1); }

void SSD1309::commands(const uint8_t *buf, size_t len) {
    beginTx(false);
    for (size_t i = 0; i < len; i++) SPI.transfer(buf[i]);
    endTx();
}

void SSD1309::data(const uint8_t *buf, size_t len) {
    beginTx(true);
    SPI.transfer(buf, nullptr, len);
    endTx();
}

void SSD1309::writeRegion(uint8_t x, uint8_t page, uint8_t w, uint8_t pages, const uint8_t *buf) {
    if (x >= WIDTH || page >= PAGES || w == 0 || pages == 0) return;
    if (x + w > WIDTH) w = WIDTH - x;
    if (page + pages > PAGES) pages = PAGES - page;
    const uint8_t win[] = {
        0x21, x, (uint8_t)(x + w - 1),
        0x22, page, (uint8_t)(page + pages - 1),
    };
    commands(win, sizeof(win));
    data(buf, (size_t)w * pages);
}

void SSD1309::fill(uint8_t pattern) {
    uint8_t row[WIDTH];
    memset(row, pattern, sizeof(row));
    const uint8_t win[] = {0x21, 0, WIDTH - 1, 0x22, 0, PAGES - 1};
    commands(win, sizeof(win));
    for (uint8_t p = 0; p < PAGES; p++) data(row, sizeof(row));
}

void SSD1309::setContrast(uint8_t v) {
    const uint8_t c[] = {0x81, v};
    commands(c, sizeof(c));
}

void SSD1309::setInvert(bool inv) { command(inv ? 0xA7 : 0xA6); }

void SSD1309::setPower(bool on) { command(on ? 0xAF : 0xAE); }

void SSD1309::setFlip(bool flip180) {
    const uint8_t c[] = {(uint8_t)(flip180 ? 0xA0 : 0xA1), (uint8_t)(flip180 ? 0xC0 : 0xC8)};
    commands(c, sizeof(c));
}
