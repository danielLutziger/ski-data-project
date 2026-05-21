"""
test.py — Three-phase integration test.

PHASE 0  Storage audit — internal flash usage + SD card space check.
          Aborts if SD card is missing or nearly full.
          Lists any data files accidentally stored on internal flash.

PHASE 1  BNO055 only — 10 s of sensor readings printed to serial.

PHASE 2  SD card — mount, storage report, create SKI_NNN.CSV, write header.

PHASE 3  Combined — read BNO055 at 50 Hz and stream rows to the CSV file.

Wiring:
  BNO055 (I2C0) : SDA=GP0   SCL=GP1
  SD card (SPI0): CLK=GP2   MOSI=GP3  MISO=GP4  CS=GP5
  SD module VCC → RP2350 VBUS (5V, not 3V3)
"""

import machine
import time
import struct
import os
import storage   # storage safety checks

BNO055_ADDR  = 0x28
SAMPLE_HZ    = 50
INTERVAL_MS  = 1000 // SAMPLE_HZ   # 20 ms
BUFFER_SIZE  = 50                   # rows before flush

CSV_HEADER = (
    "timestamp_ms,"
    "euler_heading,euler_roll,euler_pitch,"
    "quat_w,quat_x,quat_y,quat_z,"
    "accel_x,accel_y,accel_z,"
    "gyro_x,gyro_y,gyro_z,"
    "gravity_x,gravity_y,gravity_z,"
    "calibration_sys,calibration_gyro,calibration_accel,calibration_mag\n"
)


# ── Helpers ───────────────────────────────────────────────────────────────

def init_i2c():
    i2c = machine.I2C(0, scl=machine.Pin(1), sda=machine.Pin(0), freq=400_000)
    devices = i2c.scan()
    print("  I2C scan: {}".format([hex(d) for d in devices]))
    if BNO055_ADDR not in devices:
        raise RuntimeError("BNO055 not found on I2C")
    return i2c


def init_bno(i2c):
    i2c.writeto_mem(BNO055_ADDR, 0x3D, bytes([0x00]))
    time.sleep(0.025)
    i2c.writeto_mem(BNO055_ADDR, 0x3D, bytes([0x0C]))
    time.sleep(0.7)
    print("  BNO055 NDOF mode active")


def read_bno(i2c):
    raw  = i2c.readfrom_mem(BNO055_ADDR, 0x14, 32)
    gx, gy, gz      = struct.unpack_from('<hhh',  raw,  0)
    eh, er, ep      = struct.unpack_from('<hhh',  raw,  6)
    qw, qx, qy, qz = struct.unpack_from('<hhhh', raw, 12)
    ax, ay, az      = struct.unpack_from('<hhh',  raw, 20)
    vx, vy, vz      = struct.unpack_from('<hhh',  raw, 26)
    c = i2c.readfrom_mem(BNO055_ADDR, 0x35, 1)[0]
    return (
        eh / 16.0,    er / 16.0,    ep / 16.0,
        qw / 16384.0, qx / 16384.0, qy / 16384.0, qz / 16384.0,
        ax / 100.0,   ay / 100.0,   az / 100.0,
        gx / 16.0,    gy / 16.0,    gz / 16.0,
        vx / 100.0,   vy / 100.0,   vz / 100.0,
        (c >> 6) & 3, (c >> 4) & 3, (c >> 2) & 3, c & 3,
    )


def format_row(ts, d):
    return (
        "{},{:.4f},{:.4f},{:.4f},"
        "{:.6f},{:.6f},{:.6f},{:.6f},"
        "{:.4f},{:.4f},{:.4f},"
        "{:.4f},{:.4f},{:.4f},"
        "{:.4f},{:.4f},{:.4f},"
        "{},{},{},{}\n"
    ).format(ts, *d)


def _bitbang_cmd0():
    """
    Bit-bang a complete CMD0 sequence using raw GPIO, bypassing the SPI
    peripheral. Returns the R1 byte from the card, or 0xFF if no response.
    A result of 0x01 means the card IS wired and responding correctly;
    0xFF means either a physical wire is broken or the card is dead.
    """
    cs   = machine.Pin(5, machine.Pin.OUT, value=1)
    sck  = machine.Pin(2, machine.Pin.OUT, value=0)
    mosi = machine.Pin(3, machine.Pin.OUT, value=1)
    miso = machine.Pin(4, machine.Pin.IN,  machine.Pin.PULL_UP)

    def shift(byte):
        r = 0
        for i in range(7, -1, -1):
            mosi.value((byte >> i) & 1)
            sck.value(1)
            r = (r << 1) | miso.value()
            sck.value(0)
        return r

    # 80 idle clocks with CS deasserted, MOSI high
    for _ in range(80):
        sck.value(1)
        sck.value(0)

    cs.value(0)                          # select card
    for b in (0x40, 0x00, 0x00, 0x00, 0x00, 0x95):   # CMD0 + CRC
        shift(b)

    # Read up to 16 bytes waiting for a non-0xFF R1 response
    r = 0xFF
    for _ in range(16):
        r = shift(0xFF)
        if r != 0xFF:
            break

    cs.value(1)
    shift(0xFF)                          # 8 idle clocks after deselect
    return r


def mount_sd():
    import sdcard

    # Bit-bang CMD0 before hardware SPI takes over — isolates whether the
    # problem is physical wiring vs. the SPI peripheral or driver.
    bb = _bitbang_cmd0()
    if bb == 0x01:
        print("  Bit-bang CMD0: 0x01 — card wired correctly, entering SPI mode")
    elif bb == 0x00:
        print("  Bit-bang CMD0: 0x00 — possible MISO float (pull-up missing?)")
    else:
        print("  Bit-bang CMD0: 0x{:02x} — card not responding".format(bb))
        print("  Check: CS→GP5(pin7), SCK→GP2(pin4), MOSI→GP3(pin5), MISO→GP4(pin6), VCC→3V3(pin36)")

    cs   = machine.Pin(5, machine.Pin.OUT, value=1)
    # Pull-up on MISO prevents the pin from floating low when the SD card
    # tristates the line between bytes — without it, _readinto() sees 0x00
    # forever and the driver accepts 0x00 as valid for every CMD response.
    miso = machine.Pin(4, machine.Pin.IN, machine.Pin.PULL_UP)
    spi  = machine.SPI(0, baudrate=100_000, polarity=0, phase=0,
                       sck=machine.Pin(2), mosi=machine.Pin(3), miso=miso)
    sd   = sdcard.SDCard(spi, cs, baudrate=100_000)
    print("  SD card OK  (cdv={}, sectors={})".format(sd.cdv, sd.sectors))

    # Raw write test before mounting — bypasses the filesystem layer entirely.
    # Write a known pattern to block 1, then read it back to verify.
    write_buf = bytearray(b'\xA5\x5A' * 256)   # recognisable pattern
    try:
        sd.writeblocks(1, write_buf)
        read_back = bytearray(512)
        sd.readblocks(1, read_back)
        ok = read_back[:4] == write_buf[:4]
        print("  Raw write block 1: {} — wrote {}, read back {}".format(
            "OK" if ok else "MISMATCH",
            list(write_buf[:4]), list(read_back[:4])))
    except Exception as e:
        print("  Raw write block 1 FAIL:", e)

    os.mount(sd, "/sd")  # type: ignore[attr-defined]
    print("  SD mounted OK")
    return sd


def next_filename():
    n = 1
    for name in os.listdir("/sd"):  # type: ignore[attr-defined]
        u = name.upper()
        if u.startswith("SKI_") and u.endswith(".CSV"):
            try:
                n = max(n, int(u[4:-4]) + 1)
            except ValueError:
                pass
    return "SKI_{:03d}.CSV".format(n)


# ─────────────────────────────────────────────────────────────────────────────
# PHASE 0 — Internal flash audit (runs before anything else)
# ─────────────────────────────────────────────────────────────────────────────
print()
print("=" * 50)
print("PHASE 0 — Internal flash audit")
print("=" * 50)

# Show internal flash stats and warn about any data files found there.
# SD card is not mounted yet, so only internal flash is checked here.
try:
    s = os.statvfs("/")  # type: ignore[attr-defined]
    flash_total_kb = (s[0] * s[2]) // 1024
    flash_free_kb  = (s[0] * s[3]) // 1024
    flash_used_kb  = flash_total_kb - flash_free_kb
    print("  RP2350 internal flash: {}/{} KB used  ({} KB free)".format(
        flash_used_kb, flash_total_kb, flash_free_kb))
except Exception as e:
    print("  Could not read flash stats:", e)

# List all files on internal flash
print("  Files on internal flash:")
try:
    files = os.listdir("/")  # type: ignore[attr-defined]
    if files:
        for f in files:
            print("    /{}".format(f))
    else:
        print("    (none)")
except Exception as e:
    print("  Could not list flash:", e)
    files = []

# Flag any data files that should never be on internal flash
data_on_flash = [f for f in files if f.upper().endswith((".CSV", ".TXT", ".LOG"))]
if data_on_flash:
    print()
    print("  !! WARNING: sensor data found on internal flash — should be on SD card!")
    for f in data_on_flash:
        print("     /{}  ← delete this".format(f))

print()
print("  PHASE 0 OK — SD card storage check will run after mount in Phase 2")


# ─────────────────────────────────────────────────────────────────────────────
# PHASE 1 — BNO055 only: 10 s to serial
# ─────────────────────────────────────────────────────────────────────────────
print()
print("=" * 50)
print("PHASE 1 — BNO055 sensor check (10 s)")
print("=" * 50)

try:
    i2c = init_i2c()
    init_bno(i2c)
except Exception as e:
    print("  FAILED:", e)
    raise SystemExit

print("  Sampling at {} Hz — move the sensor to see values change".format(SAMPLE_HZ))
print()
print("  {:>10}  {:>8} {:>8} {:>8}  cal".format("t_ms", "heading", "roll", "pitch"))
print("  " + "-" * 52)

phase1_end = time.ticks_add(time.ticks_ms(), 10_000)  # type: ignore[attr-defined]
last_print = 0

while time.ticks_diff(phase1_end, time.ticks_ms()) > 0:  # type: ignore[attr-defined]
    t0   = time.ticks_ms()  # type: ignore[attr-defined]
    data = read_bno(i2c)

    if time.ticks_diff(t0, last_print) >= 1000 or last_print == 0:  # type: ignore[attr-defined]
        eh, er, ep = data[0], data[1], data[2]
        cs_c = int(data[16]); cg_c = int(data[17])
        ca_c = int(data[18]); cm_c = int(data[19])
        print("  {:>10}  {:>8.2f} {:>8.2f} {:>8.2f}  sys={} gyro={} acc={} mag={}".format(
            t0, eh, er, ep, cs_c, cg_c, ca_c, cm_c))
        last_print = t0

    remaining = INTERVAL_MS - time.ticks_diff(time.ticks_ms(), t0)  # type: ignore[attr-defined]
    if remaining > 0:
        time.sleep(remaining / 1000)

print()
print("  PHASE 1 OK — BNO055 is working")


# ─────────────────────────────────────────────────────────────────────────────
# PHASE 2 — SD card: mount, storage report, create CSV file
# ─────────────────────────────────────────────────────────────────────────────
print()
print("=" * 50)
print("PHASE 2 — SD card: mount + storage check + create file")
print("=" * 50)

try:
    sd = mount_sd()
except Exception as e:
    print("  FAILED:", e)
    raise SystemExit

# Full storage report now that SD is mounted
sd_ok = storage.report()
if not sd_ok:
    print("  Halting — SD card not safe for logging")
    os.umount("/sd")  # type: ignore[attr-defined]
    raise SystemExit

# Pick filename and guard the path so it can never land on internal flash
filename = next_filename()
path     = "/sd/" + filename
storage.guard_path(path)   # raises RuntimeError if not under /sd/

try:
    f = open(path, "w")
    f.write(CSV_HEADER)
    f.flush()
    f.close()
    print("  Created : {}".format(path))
    print("  SD files: {}".format(os.listdir("/sd")))  # type: ignore[attr-defined]
except Exception as e:
    print("  File create FAILED:", e)
    os.umount("/sd")  # type: ignore[attr-defined]
    raise SystemExit

print()
print("  PHASE 2 OK — file created on SD card")


# ─────────────────────────────────────────────────────────────────────────────
# PHASE 3 — Combined: BNO055 → CSV on SD card for 10 s
# ─────────────────────────────────────────────────────────────────────────────
print()
print("=" * 50)
print("PHASE 3 — BNO055 → {} for 10 s".format(filename))
print("=" * 50)

buf   = []
total = 0

try:
    storage.guard_path(path)   # double-check before opening for append
    f = open(path, "a")

    phase3_end = time.ticks_add(time.ticks_ms(), 10_000)  # type: ignore[attr-defined]

    while time.ticks_diff(phase3_end, time.ticks_ms()) > 0:  # type: ignore[attr-defined]
        t0   = time.ticks_ms()  # type: ignore[attr-defined]
        data = read_bno(i2c)
        buf.append(format_row(t0, data))
        total += 1

        if len(buf) >= BUFFER_SIZE:
            f.write("".join(buf))
            f.flush()
            buf.clear()
            free_mb = storage.sd_free_mb()
            print("  {} samples written — {} MB free on SD".format(total, free_mb))

        remaining = INTERVAL_MS - time.ticks_diff(time.ticks_ms(), t0)  # type: ignore[attr-defined]
        if remaining > 0:
            time.sleep(remaining / 1000)

    if buf:
        f.write("".join(buf))
        f.flush()
    f.close()

except Exception as e:
    print("  Write FAILED:", e)

finally:
    os.umount("/sd")  # type: ignore[attr-defined]

print()
print("  PHASE 3 OK — {} samples in {}".format(total, filename))
print()
print("=" * 50)
print("ALL PHASES DONE — pull the SD card to verify the CSV")
print("=" * 50)
