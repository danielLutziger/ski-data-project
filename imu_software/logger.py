"""
logger.py — Buffered CSV logger for the MicroSD card.

Uses the sdcard.py block device driver (included in this firmware) mounted
via uos.  The session file stays open for the duration of logging; rows are
accumulated in RAM and flushed to disk every BUFFER_SIZE samples (~1 s).

CSV column order matches the tuple returned by BNO055.read_all():
  timestamp_ms,
  euler_heading, euler_roll, euler_pitch,
  quat_w, quat_x, quat_y, quat_z,
  accel_x, accel_y, accel_z,
  gyro_x, gyro_y, gyro_z,
  gravity_x, gravity_y, gravity_z,
  calibration_sys, calibration_gyro, calibration_accel, calibration_mag
"""

import uos
import machine
from config import (
    SPI_ID, SPI_CLK, SPI_MOSI, SPI_MISO, SPI_CS, SPI_BAUD,
    BUFFER_SIZE, CSV_LONG_PREFIX, CSV_FALLBACK_PREFIX,
)

CSV_HEADER = (
    "timestamp_ms,"
    "euler_heading,euler_roll,euler_pitch,"
    "quat_w,quat_x,quat_y,quat_z,"
    "accel_x,accel_y,accel_z,"
    "gyro_x,gyro_y,gyro_z,"
    "gravity_x,gravity_y,gravity_z,"
    "calibration_sys,calibration_gyro,calibration_accel,calibration_mag\n"
)

_MOUNT = "/sd"


def _make_spi():
    """Return a configured SPI object.  The SDCard driver reinitialises
    baudrate internally during card init, so we just bind the pins here."""
    return machine.SPI(
        SPI_ID,
        baudrate=400_000,       # conservative start; SDCard bumps this up
        polarity=0,
        phase=0,
        sck=machine.Pin(SPI_CLK),
        mosi=machine.Pin(SPI_MOSI),
        miso=machine.Pin(SPI_MISO),
    )


def _next_fallback_name():
    """Scan /sd for SKI_NNN.CSV and return the next unused name."""
    try:
        entries = uos.listdir(_MOUNT)
    except OSError:
        entries = []

    max_n = 0
    for name in entries:
        upper = name.upper()
        if upper.startswith(CSV_FALLBACK_PREFIX) and upper.endswith(".CSV"):
            try:
                num = int(upper[len(CSV_FALLBACK_PREFIX):-4])
                if num > max_n:
                    max_n = num
            except ValueError:
                pass
    return "{}{:03d}.CSV".format(CSV_FALLBACK_PREFIX, max_n + 1)


def _build_filename(rtc):
    """
    Return a filename string.
    Prefers ski_YYYYMMDD_HHMMSS.csv if an RTC is available,
    otherwise falls back to SKI_NNN.CSV with auto-incrementing number.
    """
    if rtc is not None:
        try:
            t = rtc.datetime()  # (year, month, day, weekday, hour, min, sec, subsec)
            return "{}{:04d}{:02d}{:02d}_{:02d}{:02d}{:02d}.csv".format(
                CSV_LONG_PREFIX, t[0], t[1], t[2], t[4], t[5], t[6]
            )
        except Exception:
            pass
    return _next_fallback_name()


class SDLogger:
    def __init__(self):
        self._spi      = None
        self._sd       = None
        self._file     = None
        self._buf      = []
        self._filename = None
        self._total    = 0      # samples written to disk this session

    # ── Mount / unmount ───────────────────────────────────────────────────

    def mount(self):
        """Initialise SPI, mount FAT32 SD card.  Raises OSError on failure."""
        import sdcard  # local sdcard.py driver

        self._spi = _make_spi()
        cs = machine.Pin(SPI_CS, machine.Pin.OUT, value=1)
        self._sd = sdcard.SDCard(self._spi, cs, baudrate=SPI_BAUD)

        try:
            uos.mount(self._sd, _MOUNT)
        except OSError as exc:
            # errno 16 (EBUSY) or 17 (EEXIST) means already mounted
            if exc.args[0] not in (16, 17):
                raise
        print("[SD] Mounted at {}".format(_MOUNT))

    def unmount(self):
        """Flush, close the session file, and unmount the SD card."""
        self.flush()
        if self._file:
            self._file.close()
            self._file = None
        try:
            uos.umount(_MOUNT)
        except OSError:
            pass
        print("[SD] Unmounted")

    # ── Session management ────────────────────────────────────────────────

    def open_session(self, rtc=None):
        """Create a new CSV file, write the header row, and return the filename."""
        self._filename = _build_filename(rtc)
        self._total    = 0
        path = "{}/{}".format(_MOUNT, self._filename)
        self._file = open(path, "w")
        self._file.write(CSV_HEADER)
        self._file.flush()
        print("[SD] Session file: {}".format(path))
        return self._filename

    def close_session(self):
        """Flush remaining buffer and close the file."""
        self.flush()
        if self._file:
            self._file.close()
            self._file = None
        print("[SD] Session closed — {} samples written".format(self._total))

    # ── Logging ───────────────────────────────────────────────────────────

    def log(self, ts_ms, data):
        """
        Append one sample row to the in-RAM buffer.

        ts_ms  : int   — time.ticks_ms() timestamp
        data   : tuple — 20-tuple returned by BNO055.read_all()

        Automatically flushes when the buffer reaches BUFFER_SIZE.
        Raises OSError on SD write failure (caller handles remount).
        """
        (
            eh, er, ep,
            qw, qx, qy, qz,
            ax, ay, az,
            gx, gy, gz,
            vx, vy, vz,
            cs, cg, ca, cm,
        ) = data

        row = (
            "{},{:.4f},{:.4f},{:.4f},"
            "{:.6f},{:.6f},{:.6f},{:.6f},"
            "{:.4f},{:.4f},{:.4f},"
            "{:.4f},{:.4f},{:.4f},"
            "{:.4f},{:.4f},{:.4f},"
            "{},{},{},{}\n"
        ).format(
            ts_ms,
            eh, er, ep,
            qw, qx, qy, qz,
            ax, ay, az,
            gx, gy, gz,
            vx, vy, vz,
            cs, cg, ca, cm,
        )
        self._buf.append(row)

        if len(self._buf) >= BUFFER_SIZE:
            self.flush()

    def flush(self):
        """Write all buffered rows to disk and check remaining SD space."""
        if not self._buf or self._file is None:
            return
        self._file.write("".join(self._buf))
        self._file.flush()
        self._total += len(self._buf)
        self._buf.clear()
        # Warn when SD card is getting full (check every flush, ~1 s at 50 Hz)
        import storage
        free = storage.sd_free_mb()
        if free < storage._MIN_SD_FREE_MB:
            raise OSError("SD card critically low: {} MB free — stopping".format(free))
        if free < storage._WARN_SD_FREE_MB:
            print("[WARN] SD card low: {} MB free".format(free))

    # ── Properties ────────────────────────────────────────────────────────

    @property
    def filename(self):
        return self._filename

    @property
    def samples_written(self):
        return self._total

    @property
    def buffer_len(self):
        return len(self._buf)
