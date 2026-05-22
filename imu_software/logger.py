"""
logger.py — Buffered CSV logger + structured log file for the ski IMU.

Two classes:

  FileLog   — Timestamped .log file writer.
              Messages written before the SD card is ready are held in RAM
              and flushed to disk when open() is called.

  SDLogger  — Manages the SD card mount, the CSV session file, and delegates
              all human-readable output to a FileLog instance.

CSV column order:
  datetime_cet, elapsed_ms,
  euler_heading, euler_roll, euler_pitch,
  quat_w, quat_x, quat_y, quat_z,
  accel_x, accel_y, accel_z,
  gyro_x, gyro_y, gyro_z,
  gravity_x, gravity_y, gravity_z,
  calibration_sys, calibration_gyro, calibration_accel, calibration_mag
"""

import uos
import machine
import time
from config import (
    SPI_ID, SPI_CLK, SPI_MOSI, SPI_MISO, SPI_CS, SPI_BAUD,
    BUFFER_SIZE, CSV_LONG_PREFIX, CSV_FALLBACK_PREFIX,
    CET_OFFSET_H,
)

_MOUNT = "/sd"

CSV_HEADER = (
    "datetime_cet,elapsed_ms,"
    "euler_heading,euler_roll,euler_pitch,"
    "quat_w,quat_x,quat_y,quat_z,"
    "accel_x,accel_y,accel_z,"
    "gyro_x,gyro_y,gyro_z,"
    "gravity_x,gravity_y,gravity_z,"
    "calibration_sys,calibration_gyro,calibration_accel,calibration_mag\n"
)


# ─────────────────────────────────────────────────────────────────────────────
# FileLog
# ─────────────────────────────────────────────────────────────────────────────

class FileLog:
    """
    Writes timestamped, levelled log entries to a .log file on the SD card.

    Usage:
        log = FileLog(rtc, cet_offset_h=1)
        log.info("BOOT", "Starting up")          # buffered until open()
        log.open("/sd/SKI_001.log")               # flushes backlog to file
        log.info("SD", "Mounted")
        log.flush()
        log.close()
    """

    def __init__(self, rtc=None, cet_offset_h=1):
        self._rtc        = rtc
        self._offset_h   = cet_offset_h
        self._file       = None
        self._buf        = []       # lines not yet written to file

    def set_rtc(self, rtc):
        self._rtc = rtc

    def open(self, path):
        """Open the log file and flush any messages buffered before SD was ready."""
        self._file = open(path, "w")
        if self._buf:
            self._file.write("".join(self._buf))
            self._file.flush()
            self._buf.clear()

    def close(self):
        self.flush()
        if self._file:
            self._file.close()
            self._file = None

    def flush(self):
        if self._file and self._buf:
            self._file.write("".join(self._buf))
            self._file.flush()
            self._buf.clear()

    # ── Level helpers ─────────────────────────────────────────────────────────

    def info(self, tag, msg):
        self._append("INFO ", tag, msg)

    def warn(self, tag, msg):
        self._append("WARN ", tag, msg, flush_now=True)

    def error(self, tag, msg):
        self._append("ERROR", tag, msg, flush_now=True)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _append(self, level, tag, msg, flush_now=False):
        line = "{} [{}] [{:<5}] {}\n".format(self._ts(), level, tag, msg)
        print(line, end="")        # always echo to serial (USB debug)
        self._buf.append(line)
        if flush_now and self._file:
            self.flush()

    def _ts(self):
        """Return a CET ISO-8601 timestamp string for the current moment."""
        if self._rtc is None:
            return "----T--:--:--+{:02d}:00".format(self._offset_h)
        try:
            t = self._rtc.datetime()   # (year, mon, mday, wday, hour, min, sec, sub)
            h = t[4] + self._offset_h
            day_carry = h // 24
            h %= 24
            return "{:04d}-{:02d}-{:02d}T{:02d}:{:02d}:{:02d}+{:02d}:00".format(
                t[0], t[1], t[2] + day_carry, h, t[5], t[6], self._offset_h)
        except Exception:
            return "????T??:??:??+{:02d}:00".format(self._offset_h)


# ─────────────────────────────────────────────────────────────────────────────
# SPI / filename helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_spi():
    # MISO pull-up prevents the pin from floating low when the SD card
    # tristates the line — without it the driver sees 0x00 as a valid R1
    # response and falsely passes the entire init sequence.
    miso = machine.Pin(SPI_MISO, machine.Pin.IN, machine.Pin.PULL_UP)
    return machine.SPI(
        SPI_ID,
        baudrate=400_000,   # conservative init speed; SDCard uses SPI_BAUD
        polarity=0,
        phase=0,
        sck=machine.Pin(SPI_CLK),
        mosi=machine.Pin(SPI_MOSI),
        miso=miso,
    )


def _next_fallback_name():
    """Return the next unused SKI_NNN.CSV name on /sd."""
    try:
        entries = uos.listdir(_MOUNT)
    except OSError:
        entries = []
    max_n = 0
    for name in entries:
        upper = name.upper()
        if upper.startswith(CSV_FALLBACK_PREFIX) and upper.endswith(".CSV"):
            try:
                n = int(upper[len(CSV_FALLBACK_PREFIX):-4])
                if n > max_n:
                    max_n = n
            except ValueError:
                pass
    return "{}{:03d}.CSV".format(CSV_FALLBACK_PREFIX, max_n + 1)


def _build_filename(rtc):
    """
    Return a session filename.
    Uses ski_YYYYMMDD_HHMMSS.csv when the RTC year looks realistic (>= 2024),
    otherwise falls back to SKI_NNN.CSV.
    """
    if rtc is not None:
        try:
            t = rtc.datetime()
            if t[0] >= 2024:
                return "{}{:04d}{:02d}{:02d}_{:02d}{:02d}{:02d}.csv".format(
                    CSV_LONG_PREFIX, t[0], t[1], t[2], t[4], t[5], t[6])
        except Exception:
            pass
    return _next_fallback_name()


# ─────────────────────────────────────────────────────────────────────────────
# SDLogger
# ─────────────────────────────────────────────────────────────────────────────

class SDLogger:
    """
    Manages SD card lifecycle and buffered CSV + log writing.

    Typical usage:
        log    = FileLog(rtc, CET_OFFSET_H)
        logger = SDLogger(log)
        logger.mount()
        logger.open_session(rtc)
        logger.log(t0, bno_data)
        ...
        logger.close_session()
        logger.unmount()
    """

    def __init__(self, log=None):
        self._log      = log        # FileLog instance (optional)
        self._spi      = None
        self._sd       = None
        self._file     = None       # open CSV file handle
        self._buf      = []         # CSV row buffer
        self._filename = None
        self._total    = 0          # total rows written to disk this session

        # Timestamp state (initialised in open_session)
        self._ts_date_prefix = ""
        self._ts_start_s     = 0    # seconds into day at session open (CET)
        self._ts_start_ticks = 0    # time.ticks_ms() at session open
        self._ts_tz_str      = "+{:02d}:00".format(CET_OFFSET_H)
        self._ts_cached_s    = -1   # last elapsed_s we formatted
        self._ts_cached_hms  = ""   # "HH:MM:SS" string for that second

    # ── Mount / unmount ───────────────────────────────────────────────────────

    def mount(self):
        """Initialise SPI and mount the FAT32 SD card.  Raises OSError on failure."""
        import sdcard
        self._spi = _make_spi()
        cs = machine.Pin(SPI_CS, machine.Pin.OUT, value=1)
        self._sd = sdcard.SDCard(self._spi, cs, baudrate=SPI_BAUD)
        try:
            uos.mount(self._sd, _MOUNT)
        except OSError as exc:
            if exc.args[0] not in (16, 17):   # EBUSY / EEXIST = already mounted
                raise
        self._info("SD", "Mounted at {}".format(_MOUNT))

    def unmount(self):
        """Flush buffers, close files, and unmount."""
        self.flush()
        if self._file:
            self._file.close()
            self._file = None
        if self._log:
            self._log.close()
        try:
            uos.umount(_MOUNT)
        except OSError:
            pass
        self._info("SD", "Unmounted")

    # ── Session ───────────────────────────────────────────────────────────────

    def open_session(self, rtc=None):
        """
        Create matching CSV + log files on /sd, write headers, return CSV name.
        Must be called after mount().
        """
        self._filename = _build_filename(rtc)
        self._total    = 0

        csv_path = "{}/{}".format(_MOUNT, self._filename)
        self._file = open(csv_path, "w")
        self._file.write(CSV_HEADER)
        self._file.flush()
        self._info("CSV", "Created: {}".format(csv_path))

        # Open matching .log file
        stem     = self._filename.rsplit(".", 1)[0]
        log_path = "{}/{}.log".format(_MOUNT, stem)
        if self._log:
            self._log.open(log_path)
            self._info("LOG", "Created: {}".format(log_path))

        # Initialise CET timestamp helpers
        self._init_ts(rtc)
        ts_readable = self._log._ts() if self._log else "n/a"
        self._info("LOG", "Session start (CET): {}".format(ts_readable))

        return self._filename

    def close_session(self):
        """Flush remaining buffer and close the CSV (log closed in unmount)."""
        self.flush()
        if self._file:
            self._file.close()
            self._file = None
        self._info("LOG", "Session closed — {} samples written".format(self._total))

    # ── Logging ───────────────────────────────────────────────────────────────

    def log(self, t0, data):
        """
        Append one 50 Hz sample row to the in-RAM buffer.

        t0   : int   — time.ticks_ms() at sample capture
        data : tuple — 20-tuple from BNO055.read_all()

        Flushes automatically every BUFFER_SIZE rows.
        Raises OSError on SD write failure (caller handles remount).
        """
        elapsed_ms  = time.ticks_diff(t0, self._ts_start_ticks)
        elapsed_s   = elapsed_ms // 1000

        # Re-format HH:MM:SS only when the second changes (avoids 50×/s work)
        if elapsed_s != self._ts_cached_s:
            self._ts_cached_s = elapsed_s
            total_s = self._ts_start_s + elapsed_s
            h = (total_s // 3600) % 24
            m = (total_s // 60)   % 60
            s =  total_s          % 60
            self._ts_cached_hms = "{:02d}:{:02d}:{:02d}".format(h, m, s)

        ms_part     = elapsed_ms % 1000
        datetime_cet = "{}{}.{:03d}{}".format(
            self._ts_date_prefix, self._ts_cached_hms, ms_part, self._ts_tz_str)

        (
            eh, er, ep,
            qw, qx, qy, qz,
            ax, ay, az,
            gx, gy, gz,
            vx, vy, vz,
            cs, cg, ca, cm,
        ) = data

        row = (
            "{},{},{:.4f},{:.4f},{:.4f},"
            "{:.6f},{:.6f},{:.6f},{:.6f},"
            "{:.4f},{:.4f},{:.4f},"
            "{:.4f},{:.4f},{:.4f},"
            "{:.4f},{:.4f},{:.4f},"
            "{},{},{},{}\n"
        ).format(
            datetime_cet, elapsed_ms,
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
        """Write all buffered CSV rows and flush the log buffer."""
        if self._buf and self._file:
            self._file.write("".join(self._buf))
            self._file.flush()
            self._total += len(self._buf)
            self._buf.clear()
            # Check SD free space on every flush (~1 s)
            import storage
            free = storage.sd_free_mb()
            if free < storage._MIN_SD_FREE_MB:
                raise OSError("SD critically low: {} MB free".format(free))
            if free < storage._WARN_SD_FREE_MB:
                self._warn("SD", "Low space: {} MB free".format(free))
        if self._log:
            self._log.flush()

    # ── Properties ────────────────────────────────────────────────────────────

    @property
    def filename(self):
        return self._filename

    @property
    def samples_written(self):
        return self._total

    @property
    def buffer_len(self):
        return len(self._buf)

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _init_ts(self, rtc):
        """Pre-compute timestamp state from RTC at session open."""
        self._ts_start_ticks = time.ticks_ms()
        if rtc is None:
            self._ts_date_prefix = "0000-00-00T"
            self._ts_start_s     = 0
            return
        try:
            t = rtc.datetime()   # (year, mon, mday, wday, hour, min, sec, sub)
            h = t[4] + CET_OFFSET_H
            day_carry = h // 24
            h %= 24
            cet_day = t[2] + day_carry
            self._ts_date_prefix = "{:04d}-{:02d}-{:02d}T".format(t[0], t[1], cet_day)
            self._ts_start_s     = h * 3600 + t[5] * 60 + t[6]
        except Exception:
            self._ts_date_prefix = "0000-00-00T"
            self._ts_start_s     = 0

    def _info(self, tag, msg):
        if self._log:
            self._log.info(tag, msg)
        else:
            print("[INFO ] [{}] {}".format(tag, msg))

    def _warn(self, tag, msg):
        if self._log:
            self._log.warn(tag, msg)
        else:
            print("[WARN ] [{}] {}".format(tag, msg))
