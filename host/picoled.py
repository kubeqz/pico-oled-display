"""Python wrapper for the PicoLED firmware (RP2350-Zero + SSD1309 over USB bulk).

Requires: pyusb (and libusb). Pillow is optional, needed only for image/text helpers.
"""
from __future__ import annotations

import struct
from typing import Optional

import usb.core
import usb.util

VID = 0x1209
PID = 0x0001

WIDTH = 128
HEIGHT = 64
PAGES = HEIGHT // 8
FB_SIZE = WIDTH * PAGES

REQ_MAGIC = 0xA5
RSP_MAGIC = 0x5A

CMD_PING = 0x00
CMD_INIT = 0x01
CMD_FILL = 0x02
CMD_FRAME = 0x03
CMD_REGION = 0x04
CMD_CONTRAST = 0x05
CMD_INVERT = 0x06
CMD_POWER = 0x07
CMD_FLIP = 0x08
CMD_RAW = 0x09

STATUS_TEXT = {0: "ok", 1: "unknown command", 2: "bad length", 3: "bad argument"}


class PicoLEDError(Exception):
    pass


class PicoLED:
    """Controls an SSD1309 128x64 OLED attached to the PicoLED firmware."""

    def __init__(self, vid: int = VID, pid: int = PID, serial: Optional[str] = None, timeout_ms: int = 1000):
        kwargs = {"idVendor": vid, "idProduct": pid}
        if serial is not None:
            kwargs["serial_number"] = serial
        dev = usb.core.find(**kwargs)
        if dev is None:
            raise PicoLEDError(f"PicoLED device {vid:04x}:{pid:04x} not found")
        self.dev = dev
        self.timeout = timeout_ms

        cfg = dev.get_active_configuration()
        intf = usb.util.find_descriptor(cfg, bInterfaceClass=0xFF)
        if intf is None:
            raise PicoLEDError("vendor (bulk) interface not found")
        self.intf_num = intf.bInterfaceNumber
        try:
            if dev.is_kernel_driver_active(self.intf_num):
                dev.detach_kernel_driver(self.intf_num)
        except (NotImplementedError, usb.core.USBError):
            pass
        usb.util.claim_interface(dev, self.intf_num)

        def ep(direction):
            return usb.util.find_descriptor(
                intf,
                custom_match=lambda e: usb.util.endpoint_direction(e.bEndpointAddress) == direction
                and usb.util.endpoint_type(e.bmAttributes) == usb.util.ENDPOINT_TYPE_BULK,
            )

        self.ep_out = ep(usb.util.ENDPOINT_OUT)
        self.ep_in = ep(usb.util.ENDPOINT_IN)
        if self.ep_out is None or self.ep_in is None:
            raise PicoLEDError("bulk endpoints not found")
        self._drain()

    # ---- context manager ----
    def close(self) -> None:
        if self.dev is not None:
            usb.util.release_interface(self.dev, self.intf_num)
            usb.util.dispose_resources(self.dev)
            self.dev = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # ---- transport ----
    def _drain(self) -> None:
        try:
            while True:
                self.ep_in.read(self.ep_in.wMaxPacketSize, timeout=20)
        except usb.core.USBTimeoutError:
            pass
        except usb.core.USBError:
            pass

    def _transfer(self, cmd: int, payload: bytes = b"") -> bytes:
        pkt = struct.pack("<BBH", REQ_MAGIC, cmd, len(payload)) + bytes(payload)
        self.ep_out.write(pkt, timeout=self.timeout)
        rsp = bytes(self.ep_in.read(64, timeout=self.timeout))
        if len(rsp) < 4 or rsp[0] != RSP_MAGIC:
            raise PicoLEDError(f"invalid response: {rsp.hex()}")
        if rsp[1] != cmd:
            raise PicoLEDError(f"response for cmd 0x{rsp[1]:02x}, expected 0x{cmd:02x}")
        if rsp[2] != 0:
            raise PicoLEDError(f"cmd 0x{cmd:02x} failed: {STATUS_TEXT.get(rsp[2], rsp[2])}")
        return rsp[4 : 4 + rsp[3]]

    # ---- device commands ----
    def ping(self) -> dict:
        r = self._transfer(CMD_PING)
        if r[:7] != b"PICOLED":
            raise PicoLEDError("unexpected ping reply")
        return {"version": f"{r[7]}.{r[8]}", "width": r[9], "height": r[10]}

    def init(self) -> None:
        """Hardware reset + re-run the init sequence (clears the display)."""
        self._transfer(CMD_INIT)

    def fill(self, pattern: int = 0x00) -> None:
        self._transfer(CMD_FILL, bytes([pattern & 0xFF]))

    def clear(self) -> None:
        self.fill(0x00)

    def frame(self, buf: bytes) -> None:
        """Send a full 1024-byte framebuffer in native SSD1309 page format."""
        if len(buf) != FB_SIZE:
            raise ValueError(f"frame must be {FB_SIZE} bytes")
        self._transfer(CMD_FRAME, bytes(buf))

    def region(self, x: int, page: int, w: int, pages: int, data: bytes) -> None:
        """Update a w x (pages*8) block at column x, page `page` (y = page*8)."""
        if len(data) != w * pages:
            raise ValueError("data length must be w*pages")
        self._transfer(CMD_REGION, bytes([x, page, w, pages]) + bytes(data))

    def contrast(self, value: int) -> None:
        self._transfer(CMD_CONTRAST, bytes([value & 0xFF]))

    def invert(self, on: bool = True) -> None:
        self._transfer(CMD_INVERT, bytes([1 if on else 0]))

    def power(self, on: bool = True) -> None:
        self._transfer(CMD_POWER, bytes([1 if on else 0]))

    def flip(self, rotate180: bool = True) -> None:
        self._transfer(CMD_FLIP, bytes([1 if rotate180 else 0]))

    def raw_command(self, *cmds: int) -> None:
        """Send raw SSD1309 command bytes (D/C low)."""
        self._transfer(CMD_RAW, bytes(cmds))

    # ---- Pillow helpers ----
    @staticmethod
    def image_to_frame(image, threshold: int = 128) -> bytes:
        """Convert a PIL image to a 1024-byte page-format framebuffer.

        The image is resized to 128x64 if needed; pixels >= threshold are lit.
        """
        from PIL import Image

        img = image.convert("L")
        if img.size != (WIDTH, HEIGHT):
            img = img.resize((WIDTH, HEIGHT))
        px = img.tobytes()
        fb = bytearray(FB_SIZE)
        for y in range(HEIGHT):
            bit = 1 << (y & 7)
            base = (y >> 3) * WIDTH
            row = y * WIDTH
            for x in range(WIDTH):
                if px[row + x] >= threshold:
                    fb[base + x] |= bit
        return bytes(fb)

    def show_image(self, image, threshold: int = 128) -> None:
        self.frame(self.image_to_frame(image, threshold))

    def show_text(self, text: str, font=None, xy=(0, 0), spacing: int = 2) -> None:
        """Render (multi-line) text with Pillow and display it."""
        from PIL import Image, ImageDraw, ImageFont

        img = Image.new("1", (WIDTH, HEIGHT), 0)
        draw = ImageDraw.Draw(img)
        draw.multiline_text(xy, text, fill=1, font=font or ImageFont.load_default(), spacing=spacing)
        self.show_image(img)

    @staticmethod
    def new_canvas():
        """Return (image, draw) for a blank 128x64 1-bit Pillow canvas."""
        from PIL import Image, ImageDraw

        img = Image.new("1", (WIDTH, HEIGHT), 0)
        return img, ImageDraw.Draw(img)


def _main(argv=None) -> None:
    import argparse

    ap = argparse.ArgumentParser(description="PicoLED SSD1309 USB control")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("ping")
    sub.add_parser("init")
    sub.add_parser("clear")
    p = sub.add_parser("fill"); p.add_argument("pattern", type=lambda s: int(s, 0))
    p = sub.add_parser("text"); p.add_argument("text"); p.add_argument("--size", type=int, default=0)
    p = sub.add_parser("image"); p.add_argument("path"); p.add_argument("--threshold", type=int, default=128)
    p = sub.add_parser("contrast"); p.add_argument("value", type=int)
    p = sub.add_parser("invert"); p.add_argument("state", choices=["on", "off"])
    p = sub.add_parser("power"); p.add_argument("state", choices=["on", "off"])
    p = sub.add_parser("flip"); p.add_argument("state", choices=["on", "off"])
    p = sub.add_parser("raw"); p.add_argument("bytes", nargs="+", type=lambda s: int(s, 0))
    sub.add_parser("demo")
    a = ap.parse_args(argv)

    with PicoLED() as d:
        if a.cmd == "ping":
            print(d.ping())
        elif a.cmd == "init":
            d.init()
        elif a.cmd == "clear":
            d.clear()
        elif a.cmd == "fill":
            d.fill(a.pattern)
        elif a.cmd == "text":
            font = None
            if a.size:
                from PIL import ImageFont
                font = ImageFont.load_default(size=a.size)
            d.show_text(a.text.replace("\\n", "\n"), font=font)
        elif a.cmd == "image":
            from PIL import Image
            d.show_image(Image.open(a.path), a.threshold)
        elif a.cmd == "contrast":
            d.contrast(a.value)
        elif a.cmd in ("invert", "power", "flip"):
            getattr(d, a.cmd)(a.state == "on")
        elif a.cmd == "raw":
            d.raw_command(*a.bytes)
        elif a.cmd == "demo":
            _demo(d)


def _demo(d: PicoLED) -> None:
    import math
    import time

    print(d.ping())
    img, draw = d.new_canvas()
    t0 = time.time()
    frames = 0
    while time.time() - t0 < 10:
        t = time.time() - t0
        draw.rectangle((0, 0, WIDTH - 1, HEIGHT - 1), fill=0, outline=1)
        cx = 64 + int(50 * math.sin(t * 2))
        cy = 32 + int(20 * math.cos(t * 3))
        draw.ellipse((cx - 8, cy - 8, cx + 8, cy + 8), fill=1)
        fps = frames / t if t > 0 else 0
        draw.text((3, 2), f"{fps:5.1f} fps", fill=1)
        d.show_image(img)
        frames += 1
    print(f"{frames / (time.time() - t0):.1f} fps")


if __name__ == "__main__":
    _main()
