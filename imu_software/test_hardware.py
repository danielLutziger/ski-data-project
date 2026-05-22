import machine
import time
import math
import os
import uos

from config import (
    I2C_ID, I2C_SDA, I2C_SCL, I2C_FREQ,
    BNO055_ADDR,
    SPI_ID, SPI_CLK, SPI_MOSI, SPI_MISO, SPI_CS, SPI_BAUD,
)
from bno055 import BNO055

# ─────────────────────────────────────────────────────────────────────────────
# Shared hardware handles — initialised once, reused across tests
# ─────────────────────────────────────────────────────────────────────────────

_i2c        = None
_bno        = None
_sd         = None
_sd_mounted = False


def _get_i2c():
    global _i2c
    if _i2c is None:
        _i2c = machine.I2C(
            I2C_ID,
            scl=machine.Pin(I2C_SCL),
            sda=machine.Pin(I2C_SDA),
            freq=I2C_FREQ,
        )
    return _i2c


def _get_bno():
    global _bno
    if _bno is None:
        _bno = BNO055(_get_i2c(), addr=BNO055_ADDR)
        _bno.init()
        time.sleep_ms(700)   # NDOF mode needs up to 700 ms to activate
    return _bno


def _get_sd():
    """Return an SDCard instance, reusing it if already initialised."""
    global _sd
    if _sd is None:
        import sdcard
        miso = machine.Pin(SPI_MISO, machine.Pin.IN, machine.Pin.PULL_UP)
        spi  = machine.SPI(
            SPI_ID, baudrate=400_000, polarity=0, phase=0,
            sck=machine.Pin(SPI_CLK), mosi=machine.Pin(SPI_MOSI), miso=miso,
        )
        cs   = machine.Pin(SPI_CS, machine.Pin.OUT, value=1)
        _sd  = sdcard.SDCard(spi, cs, baudrate=SPI_BAUD)
    return _sd


def _mount_sd():
    global _sd_mounted
    if not _sd_mounted:
        uos.mount(_get_sd(), "/sd")
        _sd_mounted = True


def _unmount_sd():
    global _sd_mounted
    if _sd_mounted:
        try:
            uos.umount("/sd")
        except OSError:
            pass
        _sd_mounted = False
        # _sd is intentionally kept — the SDCard object stays valid after
        # filesystem unmount and can be re-mounted without re-initialising SPI.


# ─────────────────────────────────────────────────────────────────────────────
# Test runner
# ─────────────────────────────────────────────────────────────────────────────

class _Runner:
    _COL = 30   # column width for test names

    def __init__(self):
        self._passed  = 0
        self._failed  = 0
        self._skipped = 0
        self._lines   = []   # accumulates output for the log file

    def section(self, tag, title):
        line = "\n[{:<5}] {}".format(tag, title)
        print(line)
        self._lines.append(line + "\n")

    def run(self, fn, skip_if=None):
        name = fn.__name__.replace("test_", "").replace("_", " ")
        if skip_if:
            reason = skip_if()
            if reason:
                line = "  SKIP  {:<{}} — {}".format(name, self._COL, reason)
                print(line)
                self._lines.append(line + "\n")
                self._skipped += 1
                return
        try:
            detail = fn()
            marker = "  PASS  "
            line = "{}{:<{}}{}".format(
                marker, name, self._COL,
                " — " + str(detail) if detail else "")
            self._passed += 1
        except AssertionError as exc:
            line = "  FAIL  {:<{}} — {}".format(name, self._COL, exc)
            self._failed += 1
        except Exception as exc:
            line = "  ERR   {:<{}} — {}: {}".format(
                name, self._COL, type(exc).__name__, exc)
            self._failed += 1
        print(line)
        self._lines.append(line + "\n")

    def summary(self):
        sep  = "=" * 60
        line = "Results: {} passed  {} failed  {} skipped".format(
            self._passed, self._failed, self._skipped)
        ok   = self._failed == 0
        verdict = "ALL PASS" if ok else "FAILURES DETECTED"
        print("\n" + sep)
        print("  {}".format(verdict))
        print("  " + line)
        print(sep)
        self._lines += ["\n", sep + "\n", "  {}\n".format(verdict),
                        "  {}\n".format(line), sep + "\n"]

        # Save to SD if available
        try:
            _mount_sd()
            with open("/sd/TEST_HW.log", "w") as f:
                for line in self._lines:
                    f.write(line)
                f.flush()
            print("  Results saved to /sd/TEST_HW.log")
        except Exception as exc:
            print("  Could not save to SD: {}".format(exc))

        return ok


# ─────────────────────────────────────────────────────────────────────────────
# [INFRA] Infrastructure — independent of all external hardware
# ─────────────────────────────────────────────────────────────────────────────

def test_micropython_version():
    """[independent] MicroPython is running and reports a version."""
    import sys
    v = sys.version
    assert "MicroPython" in v, "Not running MicroPython: {}".format(v)
    return v.split(";")[0].strip()


def test_internal_flash_space():
    """[independent] Internal flash has at least 10 KB free."""
    s        = os.statvfs("/")
    total_kb = (s[0] * s[2]) // 1024
    free_kb  = (s[0] * s[3]) // 1024
    used_kb  = total_kb - free_kb
    assert free_kb > 10, "Only {} KB free on flash — may be too full".format(free_kb)
    return "{}/{} KB used  ({} KB free)".format(used_kb, total_kb, free_kb)


def test_no_data_files_on_flash():
    """[independent] No .CSV/.LOG data files accidentally stored on flash."""
    bad = [f for f in os.listdir("/")
           if f.upper().endswith((".CSV", ".LOG", ".TXT"))]
    assert not bad, "Data files on internal flash: {}  — move to SD".format(bad)
    return "No data files on flash"


# ─────────────────────────────────────────────────────────────────────────────
# [PINS] GPIO pin states — independent, checked before SPI/I2C init
# ─────────────────────────────────────────────────────────────────────────────

def test_miso_pullup():
    """[independent] MISO pin can be configured with pull-up (no hard short to GND).
    Note: a powered SD module may actively drive MISO LOW before SPI init —
    that is normal behaviour and does not indicate a fault."""
    miso = machine.Pin(SPI_MISO, machine.Pin.IN, machine.Pin.PULL_UP)
    val  = miso.value()
    # We cannot assert HIGH here because the SD module legitimately drives
    # MISO before SPI takes over.  We only verify the pin is configurable.
    state = "HIGH" if val else "LOW (SD module may be driving — normal)"
    return "GP{} reads {} with pull-up".format(SPI_MISO, state)


def test_cs_pin_toggles():
    """[independent] CS (GP{}) can be driven both HIGH and LOW."""
    cs = machine.Pin(SPI_CS, machine.Pin.OUT, value=1)
    assert cs.value() == 1, "GP{} cannot be driven HIGH".format(SPI_CS)
    cs.value(0)
    assert cs.value() == 0, "GP{} cannot be driven LOW".format(SPI_CS)
    cs.value(1)   # restore to deasserted state
    return "GP{} toggles HIGH → LOW → HIGH".format(SPI_CS)


def test_sda_scl_not_shorted():
    """[independent] SDA and SCL read HIGH when not driven (I2C pull-ups present)."""
    sda = machine.Pin(I2C_SDA, machine.Pin.IN, machine.Pin.PULL_UP)
    scl = machine.Pin(I2C_SCL, machine.Pin.IN, machine.Pin.PULL_UP)
    assert sda.value() == 1, "GP{} (SDA) reads LOW — check pull-ups or short".format(I2C_SDA)
    assert scl.value() == 1, "GP{} (SCL) reads LOW — check pull-ups or short".format(I2C_SCL)
    return "GP{} (SDA) and GP{} (SCL) both HIGH".format(I2C_SDA, I2C_SCL)


# ─────────────────────────────────────────────────────────────────────────────
# [I2C] I2C bus and BNO055 register communication
# ─────────────────────────────────────────────────────────────────────────────

def test_i2c_bus_has_devices():
    """[imu] At least one device responds on the I2C bus."""
    devices = _get_i2c().scan()
    assert len(devices) > 0, (
        "No I2C devices found — check SDA=GP{}, SCL=GP{}, VCC=3.3V".format(
            I2C_SDA, I2C_SCL))
    return "Devices: {}".format([hex(d) for d in devices])


def test_bno055_i2c_address():
    """[imu] BNO055 responds at its expected address (0x{:02X}).""".format(BNO055_ADDR)
    devices = _get_i2c().scan()
    assert BNO055_ADDR in devices, (
        "BNO055 not found at 0x{:02X} — found: {}".format(
            BNO055_ADDR, [hex(d) for d in devices]))
    return "0x{:02X} present on bus".format(BNO055_ADDR)


def test_bno055_chip_id():
    """[imu] BNO055 chip ID register (0x00) returns 0xA0."""
    chip_id = _get_i2c().readfrom_mem(BNO055_ADDR, 0x00, 1)[0]
    assert chip_id == 0xA0, (
        "Chip ID = 0x{:02X} (expected 0xA0) — "
        "wrong device or register map mismatch".format(chip_id))
    return "Chip ID = 0x{:02X}  ✓".format(chip_id)


def test_bno055_self_test_result():
    """[imu] BNO055 internal self-test reports all sub-systems OK."""
    # Switch to CONFIG mode to read ST_RESULT
    i2c = _get_i2c()
    i2c.writeto_mem(BNO055_ADDR, 0x3D, bytes([0x00]))   # CONFIG mode
    time.sleep_ms(25)
    # Trigger self-test via SYS_TRIGGER register (0x3F)
    i2c.writeto_mem(BNO055_ADDR, 0x3F, bytes([0x01]))
    time.sleep_ms(400)
    result = i2c.readfrom_mem(BNO055_ADDR, 0x36, 1)[0]
    # Bits 3-0: MCU, GYR, MAG, ACC — 1 = passed
    failed = []
    if not (result & 0x01): failed.append("ACC")
    if not (result & 0x02): failed.append("MAG")
    if not (result & 0x04): failed.append("GYR")
    if not (result & 0x08): failed.append("MCU")
    assert not failed, "Self-test failed for: {}  (ST_RESULT=0x{:02X})".format(
        failed, result)
    # Restore NDOF mode for subsequent tests
    i2c.writeto_mem(BNO055_ADDR, 0x3D, bytes([0x0C]))
    time.sleep_ms(20)
    return "ST_RESULT=0x{:02X}  ACC MAG GYR MCU all pass".format(result)


# ─────────────────────────────────────────────────────────────────────────────
# [SPI] Raw SPI SD card driver — block device level
# ─────────────────────────────────────────────────────────────────────────────

def test_sd_driver_init():
    """[sd] SDCard driver initialises without error (CMD0→CMD8→ACMD41→CMD9)."""
    sd = _get_sd()
    assert sd.sectors > 0, "sectors = {} (invalid)".format(sd.sectors)
    size_mb = (sd.sectors * 512) // (1024 * 1024)
    return "cdv={}  sectors={}  (~{} MB)".format(sd.cdv, sd.sectors, size_mb)


def test_sd_block_read():
    """[sd] Single block (512 B) can be read from the SD card."""
    buf = bytearray(512)
    # Use block 10 — blocks 0-3 can have a first-access delay on some cards
    # immediately after init; higher blocks respond consistently.
    _get_sd().readblocks(10, buf)
    non_zero = sum(1 for b in buf if b != 0)
    return "Block 10 read OK  ({} non-zero bytes)".format(non_zero)


def test_sd_write_read_verify():
    """[sd] Known pattern written to a scratch block matches on read-back."""
    PATTERN = bytearray(b'\xA5\x5A\xF0\x0F' * 128)   # 512 bytes, distinctive
    sd = _get_sd()

    # Save original content so we can restore it
    original = bytearray(512)
    sd.readblocks(2, original)

    try:
        sd.writeblocks(2, PATTERN)
        readback = bytearray(512)
        sd.readblocks(2, readback)
        assert readback == PATTERN, "Data mismatch — {} bytes differ".format(
            sum(1 for a, b in zip(readback, PATTERN) if a != b))
        return "512 B written and verified on block 2"
    finally:
        sd.writeblocks(2, original)   # restore original content


def test_sd_multi_block_write():
    """[sd] Multi-block write (CMD25) followed by read-verify works correctly."""
    sd   = _get_sd()
    N    = 4   # 4 × 512 = 2 KB
    # bytearray * int is not supported in MicroPython — build via bytes then cast
    DATA = bytearray(b'\xDE\xAD\xBE\xEF' * (128 * N))

    saved = bytearray(N * 512)
    sd.readblocks(10, saved)

    try:
        sd.writeblocks(10, DATA)
        result = bytearray(N * 512)
        sd.readblocks(10, result)
        assert result == DATA, "Multi-block data mismatch"
        return "{} KB written and verified (blocks 10–{})".format(N // 2, 10 + N - 1)
    finally:
        sd.writeblocks(10, saved)


# ─────────────────────────────────────────────────────────────────────────────
# [FS] FAT32 filesystem — requires SD card driver to be working
# ─────────────────────────────────────────────────────────────────────────────

def _sd_not_init():
    try:
        _get_sd()
        return None
    except Exception as e:
        return "SD driver failed: {}".format(e)


def test_sd_mount_unmount():
    """[sd] FAT32 filesystem mounts and unmounts without error."""
    _mount_sd()
    entries = uos.listdir("/sd")
    _unmount_sd()
    return "Mounted OK  ({} top-level entries)".format(len(entries))


def test_sd_free_space():
    """[sd] SD card has at least 50 MB free (minimum for a logging session)."""
    _mount_sd()
    s        = uos.statvfs("/sd")
    total_mb = (s[0] * s[2]) // (1024 * 1024)
    free_mb  = (s[0] * s[3]) // (1024 * 1024)
    pct_used = 100 * (total_mb - free_mb) // total_mb if total_mb else 0
    assert free_mb >= 50, "Only {} MB free — need at least 50 MB".format(free_mb)
    return "{} MB free / {} MB total  ({}% used)".format(free_mb, total_mb, pct_used)


def test_sd_create_read_delete_file():
    """[sd] A file can be created, written, read back, and deleted on /sd."""
    _mount_sd()
    path    = "/sd/TEST_HW_TMP.TXT"
    payload = "ski-imu-test-ok\n"
    try:
        with open(path, "w") as f:
            f.write(payload)
        with open(path, "r") as f:
            content = f.read()
        assert content == payload, "File content mismatch"
        return "Write/read OK  ({} bytes)".format(len(payload))
    finally:
        try:
            uos.remove(path)
        except OSError:
            pass


# ─────────────────────────────────────────────────────────────────────────────
# [IMU] BNO055 sensor output — requires BNO055 in NDOF mode
# ─────────────────────────────────────────────────────────────────────────────

def _bno_not_init():
    try:
        _get_bno()
        return None
    except Exception as e:
        return "BNO055 init failed: {}".format(e)


def test_bno055_ndof_mode_active():
    """[imu] OPR_MODE register confirms NDOF mode (0x0C) after init."""
    mode = _get_i2c().readfrom_mem(BNO055_ADDR, 0x3D, 1)[0]
    assert mode == 0x0C, "OPR_MODE = 0x{:02X} (expected 0x0C NDOF)".format(mode)
    return "OPR_MODE = 0x{:02X}  (NDOF active)".format(mode)


def test_euler_angles_in_range():
    """[imu] Euler angles are within physical limits (heading 0–360, roll/pitch ±180)."""
    h, r, p = _get_bno().euler()
    assert 0.0 <= h <= 360.0, "Heading out of range: {:.2f}°".format(h)
    assert -180.0 <= r <= 180.0, "Roll out of range: {:.2f}°".format(r)
    assert -180.0 <= p <= 180.0, "Pitch out of range: {:.2f}°".format(p)
    return "h={:.1f}°  r={:.1f}°  p={:.1f}°".format(h, r, p)


def test_quaternion_is_unit():
    """[imu] Quaternion magnitude is within 1% of 1.0 (unit quaternion invariant)."""
    w, x, y, z = _get_bno().quaternion()
    mag = math.sqrt(w*w + x*x + y*y + z*z)
    assert 0.99 <= mag <= 1.01, (
        "|q| = {:.5f} (expected 1.000 ±0.01) — "
        "sensor may not be fully initialised".format(mag))
    return "|q| = {:.5f}  (w={:.3f} x={:.3f} y={:.3f} z={:.3f})".format(
        mag, w, x, y, z)


def test_gravity_vector_magnitude():
    """[imu] Gravity vector magnitude is within 15% of 9.81 m/s²."""
    gx, gy, gz = _get_bno().gravity()
    mag = math.sqrt(gx*gx + gy*gy + gz*gz)
    assert 8.3 <= mag <= 11.3, (
        "|g| = {:.3f} m/s² (expected 9.81 ±15%) — "
        "check BNO055 is not on a vibrating surface".format(mag))
    return "|g| = {:.3f} m/s²  (x={:.2f} y={:.2f} z={:.2f})".format(
        mag, gx, gy, gz)


def test_linear_accel_near_zero_at_rest():
    """[imu] Linear acceleration is close to 0 when the sensor is stationary."""
    ax, ay, az = _get_bno().linear_accel()
    mag = math.sqrt(ax*ax + ay*ay + az*az)
    assert mag < 1.5, (
        "Linear accel = {:.3f} m/s² (expected <1.5 at rest) — "
        "move sensor less or wait for calibration".format(mag))
    return "|a_lin| = {:.3f} m/s²  (sensor at rest)".format(mag)


def test_calibration_status_readable():
    """[imu] Calibration registers return values in the valid range 0–3."""
    sys, gyro, accel, mag = _get_bno().calibration()
    for name, val in (("sys", sys), ("gyro", gyro), ("accel", accel), ("mag", mag)):
        assert 0 <= val <= 3, "{} calibration = {} (must be 0–3)".format(name, val)
    return "sys={} gyro={} acc={} mag={}{}".format(
        sys, gyro, accel, mag,
        "  (fully calibrated)" if all(v == 3 for v in (sys, gyro, accel, mag)) else "")


def test_sample_rate_at_50hz():
    """[imu] 50 Hz loop (read + 20 ms sleep) completes without overruns for 1 s."""
    from config import SAMPLE_INTERVAL_MS
    bno      = _get_bno()
    overruns = 0
    count    = 0
    deadline = time.ticks_add(time.ticks_ms(), 1000)  # type: ignore[attr-defined]
    while time.ticks_diff(deadline, time.ticks_ms()) > 0:  # type: ignore[attr-defined]
        t0 = time.ticks_ms()  # type: ignore[attr-defined]
        bno.read_all()
        count += 1
        elapsed   = time.ticks_diff(time.ticks_ms(), t0)  # type: ignore[attr-defined]
        remaining = SAMPLE_INTERVAL_MS - elapsed
        if remaining > 0:
            time.sleep(remaining / 1000)
        else:
            overruns += 1
    assert overruns == 0, (
        "{} overruns in {} samples — read_all() takes >{}ms".format(
            overruns, count, SAMPLE_INTERVAL_MS))
    return "{} samples, 0 overruns  ({}ms budget per sample)".format(
        count, SAMPLE_INTERVAL_MS)


def test_sensor_data_changes_over_time():
    """[imu] Sensor readings are not frozen — values differ between two reads 200 ms apart."""
    bno = _get_bno()
    d1  = bno.read_all()
    time.sleep_ms(200)
    d2  = bno.read_all()
    # Gyro (indices 10-12) always has thermal noise even when still
    gyro_delta = sum(abs(d2[i] - d1[i]) for i in (10, 11, 12))
    assert gyro_delta > 0.0 or any(d2[i] != d1[i] for i in range(16)), (
        "All 16 sensor fields identical across 200 ms — "
        "sensor may be frozen or returning stale data")
    return "Gyro Δ = {:.4f} °/s over 200 ms".format(gyro_delta)


def test_all_fields_are_floats():
    """[imu] read_all() returns a 20-tuple of numeric values (no None / exceptions)."""
    data = _get_bno().read_all()
    assert len(data) == 20, "read_all() returned {} items (expected 20)".format(len(data))
    for i, v in enumerate(data):
        assert isinstance(v, (int, float)), (
            "Field {} is {} (expected number)".format(i, type(v).__name__))
    return "20-tuple returned  all values numeric"


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def run_all():
    r = _Runner()

    print("\n" + "=" * 60)
    print("  Ski IMU — Hardware Test Suite")
    print("=" * 60)

    r.section("INFRA", "Infrastructure")
    r.run(test_micropython_version)
    r.run(test_internal_flash_space)
    r.run(test_no_data_files_on_flash)

    r.section("PINS ", "GPIO pin states (before SPI/I2C init)")
    r.run(test_miso_pullup)
    r.run(test_cs_pin_toggles)
    r.run(test_sda_scl_not_shorted)

    r.section("I2C  ", "I2C bus and BNO055 register communication")
    r.run(test_i2c_bus_has_devices)
    r.run(test_bno055_i2c_address)
    r.run(test_bno055_chip_id)
    r.run(test_bno055_self_test_result)

    r.section("SPI  ", "SPI SD card block device driver")
    r.run(test_sd_driver_init)
    r.run(test_sd_block_read,       skip_if=_sd_not_init)
    r.run(test_sd_write_read_verify, skip_if=_sd_not_init)
    r.run(test_sd_multi_block_write, skip_if=_sd_not_init)

    r.section("FS   ", "FAT32 filesystem")
    r.run(test_sd_mount_unmount,          skip_if=_sd_not_init)
    r.run(test_sd_free_space,             skip_if=_sd_not_init)
    r.run(test_sd_create_read_delete_file, skip_if=_sd_not_init)

    r.section("IMU  ", "BNO055 sensor output validation")
    r.run(test_bno055_ndof_mode_active,       skip_if=_bno_not_init)
    r.run(test_euler_angles_in_range,         skip_if=_bno_not_init)
    r.run(test_quaternion_is_unit,            skip_if=_bno_not_init)
    r.run(test_gravity_vector_magnitude,      skip_if=_bno_not_init)
    r.run(test_linear_accel_near_zero_at_rest, skip_if=_bno_not_init)
    r.run(test_calibration_status_readable,   skip_if=_bno_not_init)
    r.run(test_sample_rate_at_50hz,           skip_if=_bno_not_init)
    r.run(test_sensor_data_changes_over_time, skip_if=_bno_not_init)
    r.run(test_all_fields_are_floats,         skip_if=_bno_not_init)

    return r.summary()


run_all()
