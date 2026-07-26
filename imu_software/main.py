import machine
import time

from config import (
    I2C_ID, I2C_SDA, I2C_SCL, I2C_FREQ,
    BNO055_ADDR,
    SAMPLE_RATE_HZ, SAMPLE_INTERVAL_MS, STARTUP_DELAY_S,
    LOG_INTERVAL_SAMPLES, CET_OFFSET_H,
)
from bno055  import BNO055
from logger  import FileLog, SDLogger
import storage


# Helpers
def _wait_bno055(bno, log):
    """Block until BNO055 responds on I2C, logging each retry."""
    while not bno.detect():
        log.warn("BNO", "BNO055 not found — retrying in 2 s")
        time.sleep(2)
    log.info("BNO", "Detected OK (chip ID 0xA0)")


def _remount(logger, log):
    """Attempt SD remount after a write error.  Halts on repeated failure."""
    log.error("SD", "Write error — attempting remount")
    try:
        logger.unmount()
        logger.mount()
        logger.open_session()
        log.info("SD", "Remount OK — continuing log")
    except OSError as exc:
        log.error("SD", "Remount failed: {}  Halting.".format(exc))
        while True:
            time.sleep(10)


# Main
def main():
    # RTC (needed early so log timestamps are correct)
    try:
        rtc = machine.RTC()
    except Exception:
        rtc = None

    # FileLog: created before SD is mounted so boot messages are buffered ───
    log = FileLog(rtc=rtc, cet_offset_h=CET_OFFSET_H)

    log.info("BOOT", "=" * 44)
    log.info("BOOT", "  Ski IMU Logger — RP2350 + BNO055")
    log.info("BOOT", "=" * 44)
    log.info("BOOT", "Waiting {} s for BNO055 to settle".format(STARTUP_DELAY_S))
    time.sleep(STARTUP_DELAY_S)

    # I2C + BNO055
    i2c = machine.I2C(
        I2C_ID,
        scl=machine.Pin(I2C_SCL),
        sda=machine.Pin(I2C_SDA),
        freq=I2C_FREQ,
    )
    found = i2c.scan()
    log.info("I2C", "Scan: {}".format([hex(d) for d in found]))

    bno = BNO055(i2c, addr=BNO055_ADDR)
    _wait_bno055(bno, log)
    bno.init()

    # Internal flash audit (SD not mounted yet)
    log.info("FLASH", "Internal flash audit:")
    try:
        import os
        s = os.statvfs("/")
        total_kb = (s[0] * s[2]) // 1024
        free_kb  = (s[0] * s[3]) // 1024
        used_kb  = total_kb - free_kb
        log.info("FLASH", "{}/{} KB used  ({} KB free)".format(used_kb, total_kb, free_kb))
        for f in os.listdir("/"):
            log.info("FLASH", "  /{}".format(f))
    except Exception as exc:
        log.warn("FLASH", "Could not read flash: {}".format(exc))

    # SD card
    logger = SDLogger(log=log)
    try:
        logger.mount()
    except OSError as exc:
        log.error("SD", "Mount failed: {}  Halting.".format(exc))
        while True:
            time.sleep(10)

    # Full storage report (SD now mounted)
    sd_ok = storage.report()
    if not sd_ok:
        log.error("SD", "Storage check failed — SD full or missing.  Halting.")
        while True:
            time.sleep(10)

    # Open session (CSV + LOG files created here)
    fname = logger.open_session(rtc=rtc)
    storage.guard_path("/sd/" + fname)

    log.info("LOG", "Sample rate : {} Hz  ({} ms interval)".format(
        SAMPLE_RATE_HZ, SAMPLE_INTERVAL_MS))
    log.info("LOG", "Logging started — running unattended")

    # Sampling loop
    sample_total   = 0
    rate_count     = 0
    rate_window_t  = time.ticks_ms()
    achieved_hz    = 0
    overrun_count  = 0
    next_log_at    = LOG_INTERVAL_SAMPLES    # sample count for next health line

    try:
        while True:
            t0 = time.ticks_ms()

            data = bno.read_all()

            try:
                logger.log(t0, data)
            except OSError:
                _remount(logger, log)

            sample_total += 1
            rate_count   += 1

            # 1 Hz rate window
            now = time.ticks_ms()
            if time.ticks_diff(now, rate_window_t) >= 1000:
                achieved_hz   = rate_count
                rate_count    = 0
                rate_window_t = now
                if achieved_hz < SAMPLE_RATE_HZ - 5:
                    log.warn("RATE", "Below target: {} Hz (target {} Hz)".format(
                        achieved_hz, SAMPLE_RATE_HZ))

            # Health summary every LOG_INTERVAL_SAMPLES
            if sample_total >= next_log_at:
                next_log_at += LOG_INTERVAL_SAMPLES
                cs, cg, ca, cm = int(data[16]), int(data[17]), int(data[18]), int(data[19])
                free_mb = storage.sd_free_mb()

                # Format total as "1k", "10k", etc. for readability
                if sample_total >= 1000:
                    count_str = "{}k".format(sample_total // 1000)
                    if sample_total % 1000:
                        count_str = "{}.{}k".format(
                            sample_total // 1000, (sample_total % 1000) // 100)
                else:
                    count_str = str(sample_total)

                log.info("LOG", (
                    "{} entries written | {} Hz | buf={} | "
                    "cal sys={} gyro={} acc={} mag={} | {} MB free"
                ).format(
                    count_str, achieved_hz, logger.buffer_len,
                    cs, cg, ca, cm, free_mb,
                ))

            # Timing
            elapsed   = time.ticks_diff(time.ticks_ms(), t0)
            remaining = SAMPLE_INTERVAL_MS - elapsed
            if remaining > 0:
                time.sleep_ms(remaining)
            else:
                overrun_count += 1
                if overrun_count % 100 == 0:
                    log.warn("RATE", "{} loop overruns (last={} ms)".format(
                        overrun_count, elapsed))

    except KeyboardInterrupt:
        log.info("LOG", "KeyboardInterrupt — closing session")

    finally:
        logger.close_session()
        logger.unmount()
        log.info("LOG", "Done.  Total samples: {}".format(sample_total))


main()
