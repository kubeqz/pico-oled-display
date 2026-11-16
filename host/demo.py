"""Animated demo mode for PicoLED."""
from __future__ import annotations

import math
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from picoled import PicoLED


def run(d: PicoLED, width: int, height: int) -> None:
    print(d.ping())
    img, draw = d.new_canvas()
    t0 = time.time()
    frames = 0
    while time.time() - t0 < 100:
        t = time.time() - t0
        draw.rectangle((0, 0, width - 1, height - 1), fill=0, outline=1)
        cx = 64 + int(50 * math.sin(t * 2))
        cy = 32 + int(20 * math.cos(t * 3))
        draw.ellipse((cx - 8, cy - 8, cx + 8, cy + 8), fill=1)
        fps = frames / t if t > 0 else 0
        draw.text((3, 2), f"{fps:5.1f} fps", fill=1)
        d.show_image(img)
        frames += 1
    print(f"{frames / (time.time() - t0):.1f} fps")


if __name__ == "__main__":
    from picoled import HEIGHT, WIDTH, PicoLED

    with PicoLED() as device:
        run(device, WIDTH, HEIGHT)
