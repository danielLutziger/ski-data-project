"""
led.py — LED status indicator patterns for the ski logger.

Patterns:
  INIT       — solid ON during boot
  LOGGING    — 1 Hz (100 ms on / 900 ms off); call tick_logging() each loop
  ERROR      — 10 Hz fast blink (blocking, used while retrying)
  SD_ERROR   — 3-short / 3-long / 3-short SOS (blocking, used on fatal halt)
"""

import machine
import time
from config import LED_PIN


class LED:
    def __init__(self):
        self._pin = machine.Pin(LED_PIN, machine.Pin.OUT)
        self._pin.off()

    # ── Primitives ────────────────────────────────────────────────────────

    def on(self):
        self._pin.on()

    def off(self):
        self._pin.off()

    # ── Blocking patterns ─────────────────────────────────────────────────

    def blink(self, times, on_ms=100, off_ms=100):
        """Blink *times* times, then leave LED off."""
        for _ in range(times):
            self._pin.on()
            time.sleep_ms(on_ms)
            self._pin.off()
            time.sleep_ms(off_ms)

    def error_fast(self, duration_ms=2000):
        """10 Hz blink for *duration_ms* ms. Used while retrying BNO055."""
        deadline = time.ticks_add(time.ticks_ms(), duration_ms)
        while time.ticks_diff(deadline, time.ticks_ms()) > 0:
            self._pin.on()
            time.sleep_ms(50)
            self._pin.off()
            time.sleep_ms(50)

    def sd_error_pattern(self):
        """
        One SOS cycle (3 short / 3 long / 3 short) then a 1 s pause.
        Call in a tight loop to signal a fatal SD failure:
            while True:
                led.sd_error_pattern()
        """
        self.blink(3, on_ms=100, off_ms=100)   # · · ·
        time.sleep_ms(200)
        self.blink(3, on_ms=300, off_ms=100)   # — — —
        time.sleep_ms(200)
        self.blink(3, on_ms=100, off_ms=100)   # · · ·
        time.sleep_ms(1000)

    # ── Non-blocking tick (call once per main loop iteration) ─────────────

    def tick_logging(self, ticks_now_ms):
        """
        Produce a 1 Hz blink without blocking.
        On for the first 100 ms of each 1000 ms window, off otherwise.
        Pass time.ticks_ms() as ticks_now_ms.
        """
        self._pin.value(1 if (ticks_now_ms % 1000) < 100 else 0)
