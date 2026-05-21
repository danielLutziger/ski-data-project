"""
main.py — Entry point for the RP2350-Zero ski IMU data logger.

Boot sequence:
  1. LED solid ON during hardware init
  2. 3 s startup delay  (BNO055 power-on settling time)
  3. Mount SD card       → fatal SOS blink if it fails
  4. Detect BNO055       → fast-blink + 2 s retry until found
  5. Open CSV session
  6. Sample at 50 Hz; flush to SD every 50 samples (~1 s)
  7. 1 Hz LED heartbeat while logging
  8. Ctrl-C or power-loss → close session gracefully
"""

import machine
import time

from config  import (
    I2C_ID, I2C_SDA, I2C_SCL, I2C_FREQ,
    BNO055_ADDR,
    SAMPLE_RATE_HZ, SAMPLE_INTERVAL_MS, STARTUP_DELAY_S,
)
from bno055   import BNO055
from logger   import SDLogger
import storage


# ── Helper: fatal SD halt ─────────────────────────────────────────────────

def _halt_sd(msg): #led, msg):
    print("[FATAL] {}  Halting.".format(msg))
    #while True:
    #    led.sd_error_pattern()


# ── Helper: wait for BNO055 ───────────────────────────────────────────────

def _wait_bno055(bno):#, led):
    while not bno.detect():
        print("[WARN] BNO055 not found on I2C — retrying in 2 s …")
        #led.error_fast(2000)
    print("[OK]   BNO055 detected (chip ID 0xA0)")


# ── Helper: attempt SD remount after write error ──────────────────────────

def _remount(logger):#, led):
    print("[WARN] SD write error — attempting remount …")
    try:
        logger.unmount()
        logger.mount()
        logger.open_session()
        print("[OK]   SD remounted; continuing log")
    except OSError as exc:
        _halt_sd("SD remount failed: {}".format(exc))
        #_halt_sd(led, "SD remount failed: {}".format(exc))


# ── Main ──────────────────────────────────────────────────────────────────

def main():
    #led = LED()
    #led.on()        # solid ON during init
    print()
    print("=" * 48)
    print("  Ski IMU Logger — RP2350-Zero + BNO055")
    print("=" * 48)

    # ── 1. Startup delay ──────────────────────────────────────────────────
    print("[BOOT] Waiting {} s for BNO055 to settle …".format(STARTUP_DELAY_S))
    time.sleep(STARTUP_DELAY_S)

    # ── 2. I2C + BNO055 ──────────────────────────────────────────────────
    i2c = machine.I2C(
        I2C_ID,
        scl=machine.Pin(I2C_SCL),
        sda=machine.Pin(I2C_SDA),
        freq=I2C_FREQ,
    )
    found = i2c.scan()
    print("[I2C]  Devices on bus: {}".format([hex(d) for d in found]))

    bno = BNO055(i2c, addr=BNO055_ADDR)
    _wait_bno055(bno) #, led)
    bno.init()

    # ── 3. Internal flash audit ───────────────────────────────────────────
    storage.report()   # prints flash usage; SD not mounted yet so only flash shown

    # ── 4. SD card ────────────────────────────────────────────────────────
    logger = SDLogger()
    try:
        logger.mount()
    except OSError as exc:
        _halt_sd("SD mount failed: {}".format(exc))

    # Full storage report now SD is mounted — halts if card is unsafe
    if not storage.report():
        _halt_sd("SD storage check failed")

    # ── 5. Open session ───────────────────────────────────────────────────
    try:
        rtc = machine.RTC()
    except Exception:
        rtc = None

    fname = logger.open_session(rtc=rtc)
    storage.guard_path("/sd/" + fname)   # ensures file is on SD, not flash
    print("[LOG]  Filename    : {}".format(fname))
    print("[LOG]  Sample rate : {} Hz  ({} ms interval)".format(
        SAMPLE_RATE_HZ, SAMPLE_INTERVAL_MS))

    #led.off()
    print("[LOG]  Logging started — Ctrl-C to stop gracefully")
    print()

    # ── 5. Logging loop ───────────────────────────────────────────────────
    sample_total   = 0
    rate_count     = 0          # samples in current 1 s window
    rate_window_t  = time.ticks_ms()
    achieved_hz    = 0
    overrun_count  = 0

    try:
        while True:
            t0 = time.ticks_ms()

            # Read all sensor fields (two I2C transactions)
            data = bno.read_all()

            # Buffer the row; flush triggers automatically at BUFFER_SIZE
            try:
                logger.log(t0, data)
            except OSError:
                _remount(logger) #, led)

            sample_total += 1
            rate_count   += 1

            # ── 1 Hz diagnostics ─────────────────────────────────────────
            now = time.ticks_ms()
            if time.ticks_diff(now, rate_window_t) >= 1000:
                achieved_hz   = rate_count
                rate_count    = 0
                rate_window_t = now

                # Calibration is the last 4 elements of the 20-tuple
                cs, cg, ca, cm = data[16], data[17], data[18], data[19]
                print(
                    "[LOG]  {:>6} samples | {:2d} Hz | buf={:2d} | "
                    "cal sys={} gyro={} acc={} mag={}".format(
                        sample_total, achieved_hz, logger.buffer_len,
                        cs, cg, ca, cm,
                    )
                )

                if achieved_hz < SAMPLE_RATE_HZ - 5:
                    print("[WARN] Rate below target ({} Hz achieved)".format(achieved_hz))

            # ── LED heartbeat ─────────────────────────────────────────────
            #led.tick_logging(t0)

            # ── Timing: sleep the unused portion of the 20 ms slot ────────
            elapsed   = time.ticks_diff(time.ticks_ms(), t0)
            remaining = SAMPLE_INTERVAL_MS - elapsed
            if remaining > 0:
                time.sleep_ms(remaining)
            else:
                overrun_count += 1
                if overrun_count % 100 == 0:
                    print("[WARN] {} loop overruns (last={} ms)".format(
                        overrun_count, elapsed))

    except KeyboardInterrupt:
        print()
        print("[LOG]  KeyboardInterrupt — closing session …")

    finally:
        logger.close_session()
        logger.unmount()
        #led.off()
        print("[LOG]  Done.  Total samples: {}".format(sample_total))


main()
