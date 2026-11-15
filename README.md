# PicoLED: SSD1309 OLED over USB on the RP2350-Zero

Firmware for the **Waveshare RP2350-Zero** that drives a **128x64 SSD1309 OLED over SPI**. A PC controls the display through a **USB vendor interface with bulk endpoints**. A **Python wrapper** (`host/picoled.py`) is included.

```
 PC (Python, pyusb) ──USB bulk OUT/IN──► RP2350-Zero ──SPI0──► SSD1309 128x64
```

## Wiring

### Schematic

```
        Waveshare RP2350-Zero                        SSD1309 OLED module (SPI)
     ┌───────────────────────────┐                  ┌──────────────────────────┐
     │                       3V3 ├──────────────────┤ VCC                      │
     │                       GND ├──────────────────┤ GND                      │
     │  GP2  (SPI0 SCK)          ├──────────────────┤ SCK  / D0 / CLK          │
     │  GP3  (SPI0 TX / MOSI)    ├──────────────────┤ SDA  / D1 / DIN / MOSI   │
     │  GP5  (chip select)       ├──────────────────┤ CS                       │
     │  GP6  (data / command)    ├──────────────────┤ DC   / A0                │
     │  GP7  (reset)             ├──────────────────┤ RES  / RST               │
     │                           │                  │                          │
     │  GP4  (SPI0 RX, reserved, │                  │  (no MISO, display is    │
     │        leave unconnected) │                  │   write-only)            │
     │                           │                  └──────────────────────────┘
     │   [USB-C] ──► to PC       │
     └───────────────────────────┘
```

### Pin table

| SSD1309 pin            | RP2350-Zero pin | Function                        |
|------------------------|-----------------|---------------------------------|
| GND                    | GND             | Ground                          |
| VCC                    | 3V3             | Power (see note below)          |
| SCK / D0 / CLK         | GP2             | SPI0 clock                      |
| SDA / D1 / DIN / MOSI  | GP3             | SPI0 data out (MOSI)            |
| CS                     | GP5             | Chip select (active low)        |
| DC / A0                | GP6             | Data (high) / command (low)     |
| RES / RST              | GP7             | Reset (active low)              |

Notes:

* **Power:** most SSD1309 modules (for example the common 2.42" boards) have an on-board regulator and boost converter and accept 3.3–5 V on VCC. Powering from 3V3 keeps the logic levels matched to the RP2350. If your module needs more current or 5 V, power it from the `5V` pin. The RP2350 drives 3.3 V logic, which SSD1309 modules accept.
* **Interface mode:** many modules ship configured for SPI. If yours has `BS1/BS2` jumpers or resistors, set them for **4-wire SPI**. On some modules, I²C mode needs resistor changes.
* **GP4** (SPI0 RX) is claimed by the SPI peripheral but not used, so leave it unconnected.
* The on-board WS2812 LED (GP16) is not used.
* To use other pins, override them with build flags in `platformio.ini`, for example:
  `-DOLED_PIN_DC=8 -DOLED_PIN_RST=9`. SCK and MOSI must be valid SPI0 pins (SCK: GP2/6/18, TX: GP3/7/19).

## Project layout

```
platformio.ini         PlatformIO config (arduino-pico core, TinyUSB)
src/main.cpp           USB vendor interface + command parser
src/protocol.h         USB protocol definitions (commands, status codes)
src/ssd1309.h/.cpp     Minimal SSD1309 SPI driver
host/picoled.py        Python wrapper + command-line tool
host/requirements.txt  Python dependencies
host/99-picoled.rules  Linux udev rule for non-root access
```

## Building and flashing the firmware

The project uses the community [platform-raspberrypi](https://github.com/maxgerhardt/platform-raspberrypi) with Earle Philhower's [arduino-pico](https://github.com/earlephilhower/arduino-pico) core. The official PlatformIO `raspberrypi` platform does not support the RP2350. The first build downloads the toolchain and core, which takes several minutes.

```bash
pio run                   # build -> .pio/build/rp2350zero/firmware.uf2
pio run -t upload         # flash (board must be in BOOTSEL mode or running this firmware)
```

To flash manually, hold **BOOT** while plugging in USB (or while pressing RESET). Then copy `.pio/build/rp2350zero/firmware.uf2` to the `RP2350` drive.

> **Important: path with a backslash.** If the project folder name contains a `\` (for example `Projects\picoled`), linking fails with `cannot open linker script file .../memmap_default.ld`. The backslash is dropped from the linker script path. Rename the folder (for example to `Projects/picoled`) to fix it.

At startup the firmware initializes the display and draws a 1-pixel border. That confirms the wiring works before you connect from the PC.

### Configuration (build flags)

| Macro              | Default    | Description                    |
|--------------------|------------|--------------------------------|
| `OLED_PIN_SCK`     | `2`        | SPI0 SCK pin                   |
| `OLED_PIN_MOSI`    | `3`        | SPI0 TX pin                    |
| `OLED_PIN_CS`      | `5`        | Chip select                    |
| `OLED_PIN_DC`      | `6`        | Data/command                   |
| `OLED_PIN_RST`     | `7`        | Reset                          |
| `OLED_SPI_HZ`      | `8000000`  | SPI clock (SSD1309 max ~10 MHz)|
| `PICOLED_USB_VID`  | `0x1209`   | USB vendor ID                  |
| `PICOLED_USB_PID`  | `0x0001`   | USB product ID                 |

`0x1209:0x0001` is the [pid.codes](https://pid.codes) test ID. For a released product, use your own VID/PID and pass it to the Python wrapper (`PicoLED(vid=..., pid=...)`).

## USB interface

The device enumerates as a composite device, **"PicoLED SSD1309"**, with:

* a **CDC serial** port, created by the core and usable for debugging, and
* a **vendor-specific interface** (class `0xFF`) with one **bulk OUT** and one **bulk IN** endpoint (64-byte packets, USB full speed).

The vendor interface comes from TinyUSB's WebUSB class. It also provides **Microsoft OS 2.0 descriptors**, so **Windows binds WinUSB automatically** with no driver install. On Linux, no kernel driver claims the interface. You only need the udev rule to access it without root.

### Protocol

All multi-byte fields are little-endian. Each request gets exactly one response.

**Request** (host → device, bulk OUT):

| Offset | Size | Field                       |
|--------|------|-----------------------------|
| 0      | 1    | magic `0xA5`                |
| 1      | 1    | command                     |
| 2      | 2    | payload length `N` (u16 LE) |
| 4      | N    | payload                     |

**Response** (device → host, bulk IN):

| Offset | Size | Field                      |
|--------|------|----------------------------|
| 0      | 1    | magic `0x5A`               |
| 1      | 1    | command (echo)             |
| 2      | 1    | status                     |
| 3      | 1    | payload length `M`         |
| 4      | M    | payload                    |

**Commands:**

| Code   | Name       | Payload                                   | Response payload                                 |
|--------|------------|-------------------------------------------|--------------------------------------------------|
| `0x00` | PING       | none                                      | `"PICOLED"`, ver major, ver minor, width, height |
| `0x01` | INIT       | none: hardware reset + init, clears screen | none                                            |
| `0x02` | FILL       | `pattern` (1 byte written to every page byte) | none                                         |
| `0x03` | FRAME      | 1024 bytes of framebuffer                 | none                                             |
| `0x04` | REGION     | `x, page, w, pages`, then `w*pages` bytes | none                                             |
| `0x05` | CONTRAST   | `value` (0–255)                           | none                                             |
| `0x06` | INVERT     | `0` normal / `1` inverted                 | none                                             |
| `0x07` | POWER      | `0` display off (sleep) / `1` on          | none                                             |
| `0x08` | FLIP       | `0` normal / `1` rotated 180°             | none                                             |
| `0x09` | RAW        | 1+ raw SSD1309 command bytes (D/C low)    | none                                             |

**Status codes:** `0x00` OK, `0x01` unknown command, `0x02` bad length, `0x03` bad argument.

**Framebuffer format** (native SSD130x page layout): 8 pages of 128 bytes. Byte `page*128 + x` holds pixels `(x, page*8 + 0..7)`. Bit 0 is the topmost pixel. `1` means the pixel is lit.

**Robustness:** the parser skips bytes until it sees the `0xA5` magic. If a packet stays incomplete for more than 500 ms, the parser resets, so the host can always recover.

## Python wrapper

### Setup

```bash
cd host
python3 -m pip install -r requirements.txt   # pyusb + Pillow (Pillow is optional)
```

* **Linux:** install libusb (`sudo apt install libusb-1.0-0`). For access without root, install the udev rule:
  ```bash
  sudo cp 99-picoled.rules /etc/udev/rules.d/
  sudo udevadm control --reload && sudo udevadm trigger
  ```
* **Windows:** WinUSB is bound automatically. pyusb also needs a libusb backend, for example `pip install libusb` or place `libusb-1.0.dll` on the `PATH`.
* **macOS:** `brew install libusb`.

### Command-line tool

```bash
python3 picoled.py ping                     # {'version': '1.0', 'width': 128, 'height': 64}
python3 picoled.py text "Hello\nWorld" --size 16
python3 picoled.py image picture.png --threshold 100
python3 picoled.py clear
python3 picoled.py fill 0xAA                # stripe pattern
python3 picoled.py contrast 255
python3 picoled.py invert on|off
python3 picoled.py flip on|off              # rotate 180°
python3 picoled.py power on|off
python3 picoled.py raw 0xA5                 # raw SSD1309 command(s): entire display on
python3 picoled.py init                     # re-initialize (reset) the display
python3 picoled.py demo                     # 10 s animation with FPS counter
```

### Library API

```python
from picoled import PicoLED

with PicoLED() as oled:            # PicoLED(vid=0x1209, pid=0x0001, serial=None, timeout_ms=1000)
    print(oled.ping())

    # Draw with Pillow
    img, draw = oled.new_canvas()  # 128x64 1-bit image + ImageDraw
    draw.rectangle((0, 0, 127, 63), outline=1)
    draw.text((10, 25), "Hello OLED", fill=1)
    oled.show_image(img)           # any PIL image; resized to 128x64 if needed and thresholded

    oled.show_text("Line 1\nLine 2")

    # Raw framebuffer access
    fb = bytearray(1024)
    fb[0] = 0xFF                   # 8 lit pixels at x=0, y=0..7
    oled.frame(fb)
    oled.region(x=0, page=0, w=8, pages=1, data=b"\xFF" * 8)  # partial update

    oled.contrast(128)
    oled.invert(True)
    oled.flip(True)
    oled.power(False)
    oled.raw_command(0xAF)         # display on
    oled.clear()
```

| Method                                   | Description                                                 |
|------------------------------------------|-------------------------------------------------------------|
| `ping()`                                 | Returns firmware version and display size                   |
| `init()`                                 | Hardware reset and re-init                                  |
| `fill(pattern)` / `clear()`              | Fill the screen with a byte pattern / clear it              |
| `frame(buf)`                             | Send a full 1024-byte framebuffer                           |
| `region(x, page, w, pages, data)`        | Update part of the screen (`y` = `page*8`, height = `pages*8`) |
| `contrast(v)`                            | Set contrast 0–255                                          |
| `invert(on)` / `flip(on)` / `power(on)`  | Invert colors / rotate 180° / turn the panel on or off       |
| `raw_command(*bytes)`                    | Send raw SSD1309 commands                                   |
| `image_to_frame(img, threshold)`         | Convert a PIL image to framebuffer bytes (static method)    |
| `show_image(img, threshold)`             | Convert and display a PIL image                             |
| `show_text(text, font, xy, spacing)`     | Render text with Pillow and display it                      |
| `new_canvas()`                           | Returns `(image, draw)` for a blank 128x64 canvas           |
| `close()`                                | Release the USB interface (done automatically by `with`)    |

Errors raise `PicoLEDError`, and USB timeouts raise `usb.core.USBTimeoutError`.

## Troubleshooting

| Symptom                                    | Check                                                              |
|--------------------------------------------|--------------------------------------------------------------------|
| No border at boot                          | Wiring, module set to SPI mode, VCC, and that the CS/DC/RST pins match the build flags |
| Image mirrored or upside down              | `flip(True)`, or adjust `0xA0/0xA1` and `0xC0/0xC8` in `SSD1309::init()` |
| `device not found`                         | Firmware flashed, `lsusb` shows `1209:0001`, VID/PID match         |
| `Access denied` (Linux)                    | udev rule installed and the device replugged                       |
| `No backend available`                     | Install libusb for your OS                                         |
| Link error `memmap_default.ld`             | Remove the backslash from the project path (see above)             |
