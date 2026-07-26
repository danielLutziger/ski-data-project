import struct
import time

# Register addresses
_REG_CHIP_ID  = 0x00
_REG_OPR_MODE = 0x3D
_REG_CALIB    = 0x35

_REG_GYRO_X   = 0x14   # 6 bytes: x y z  (signed 16-bit LE)
_REG_EULER_H  = 0x1A   # 6 bytes: heading roll pitch
_REG_QUAT_W   = 0x20   # 8 bytes: w x y z
_REG_LIN_ACC  = 0x28   # 6 bytes: x y z  (linear accel, gravity removed)
_REG_GRAVITY  = 0x2E   # 6 bytes: x y z

# ── Operation modes ───────────────────────────────────────────────────────
_MODE_CONFIG  = 0x00
_MODE_NDOF    = 0x0C

# ── Scale factors ─────────────────────────────────────────────────────────
_SCALE_EULER  = 16.0      # LSB/degree  → degrees
_SCALE_QUAT   = 16384.0   # LSB         → unit quaternion component
_SCALE_ACCEL  = 100.0     # LSB/(m/s²)  → m/s²
_SCALE_GYRO   = 16.0      # LSB/(deg/s) → deg/s  (see NOTE above)

_CHIP_ID_VAL  = 0xA0


class BNO055:
    def __init__(self, i2c, addr=0x28):
        self._i2c  = i2c
        self._addr = addr
        # Pre-allocated read buffers to avoid repeated heap allocation
        self._buf6 = bytearray(6)
        self._buf8 = bytearray(8)
        self._buf1 = bytearray(1)

    # ── Low-level helpers ─────────────────────────────────────────────────

    def _read_into(self, reg, buf):
        self._i2c.readfrom_mem_into(self._addr, reg, buf)

    def _write_byte(self, reg, value):
        self._buf1[0] = value
        self._i2c.writeto_mem(self._addr, reg, self._buf1)

    # ── Detection and initialisation ──────────────────────────────────────

    def detect(self):
        """Return True if a BNO055 is present and responding on I2C."""
        try:
            data = self._i2c.readfrom_mem(self._addr, _REG_CHIP_ID, 1)
            return data[0] == _CHIP_ID_VAL
        except OSError:
            return False

    def init(self):
        """
        Switch to CONFIG mode, then to NDOF fusion mode.
        Must be called once before any data read.
        """
        self._write_byte(_REG_OPR_MODE, _MODE_CONFIG)
        time.sleep_ms(25)
        self._write_byte(_REG_OPR_MODE, _MODE_NDOF)
        time.sleep_ms(20)   # datasheet: 7 ms typical, 19 ms max
        print("[BNO055] NDOF mode active")

    # ── Individual sensor reads ───────────────────────────────────────────

    def euler(self):
        """Return (heading, roll, pitch) in degrees."""
        self._read_into(_REG_EULER_H, self._buf6)
        h, r, p = struct.unpack('<hhh', self._buf6)
        return h / _SCALE_EULER, r / _SCALE_EULER, p / _SCALE_EULER

    def quaternion(self):
        """Return (w, x, y, z) unit quaternion."""
        self._read_into(_REG_QUAT_W, self._buf8)
        w, x, y, z = struct.unpack('<hhhh', self._buf8)
        s = _SCALE_QUAT
        return w / s, x / s, y / s, z / s

    def linear_accel(self):
        """Return (x, y, z) linear acceleration in m/s² (gravity removed)."""
        self._read_into(_REG_LIN_ACC, self._buf6)
        x, y, z = struct.unpack('<hhh', self._buf6)
        return x / _SCALE_ACCEL, y / _SCALE_ACCEL, z / _SCALE_ACCEL

    def gyro(self):
        """Return (x, y, z) angular velocity in deg/s."""
        self._read_into(_REG_GYRO_X, self._buf6)
        x, y, z = struct.unpack('<hhh', self._buf6)
        return x / _SCALE_GYRO, y / _SCALE_GYRO, z / _SCALE_GYRO

    def gravity(self):
        """Return (x, y, z) gravity vector in m/s²."""
        self._read_into(_REG_GRAVITY, self._buf6)
        x, y, z = struct.unpack('<hhh', self._buf6)
        return x / _SCALE_ACCEL, y / _SCALE_ACCEL, z / _SCALE_ACCEL

    def calibration(self):
        """
        Return (sys, gyro, accel, mag) calibration levels, each 0–3.
        3 = fully calibrated.  Sys = 0 means fusion output is unreliable.
        """
        self._read_into(_REG_CALIB, self._buf1)
        raw  = self._buf1[0]
        sys  = (raw >> 6) & 0x03
        gyro = (raw >> 4) & 0x03
        accel= (raw >> 2) & 0x03
        mag  =  raw       & 0x03
        return sys, gyro, accel, mag

    # ── Batched read (minimises I2C bus transactions) ─────────────────────

    def read_all(self):
        """
        Read all fields in as few I2C transactions as possible.
        Returns a 20-tuple:
          (euler_h, euler_r, euler_p,
           quat_w, quat_x, quat_y, quat_z,
           accel_x, accel_y, accel_z,
           gyro_x, gyro_y, gyro_z,
           grav_x, grav_y, grav_z,
           cal_sys, cal_gyro, cal_accel, cal_mag)

        Euler / accel / gyro / gravity registers are contiguous from
        0x14–0x35, so we read the whole block in two transactions:
          1. 0x14–0x2F (28 bytes): gyro(6) + euler(6) + quat(8) + lin_accel(6) + [2 reserved]
             Wait — the layout skips: gyro=0x14, euler=0x1A, quat=0x20, lin=0x28, gravity=0x2E
             That is contiguous: 0x14 to 0x33 = 32 bytes, then calib at 0x35.
        """
        # Read 0x14 → 0x33 inclusive = 32 bytes
        buf = bytearray(32)
        self._i2c.readfrom_mem_into(self._addr, _REG_GYRO_X, buf)

        # Gyro: offsets 0–5
        gx, gy, gz = struct.unpack_from('<hhh', buf, 0)
        # Euler: offsets 6–11
        eh, er, ep = struct.unpack_from('<hhh', buf, 6)
        # Quaternion: offsets 12–19
        qw, qx, qy, qz = struct.unpack_from('<hhhh', buf, 12)
        # Linear accel: offsets 20–25
        ax, ay, az = struct.unpack_from('<hhh', buf, 20)
        # Gravity: offsets 26–31
        vx, vy, vz = struct.unpack_from('<hhh', buf, 26)

        # Calibration: single byte at 0x35
        self._read_into(_REG_CALIB, self._buf1)
        raw  = self._buf1[0]
        cs   = (raw >> 6) & 0x03
        cg   = (raw >> 4) & 0x03
        ca   = (raw >> 2) & 0x03
        cm   =  raw       & 0x03

        return (
            eh / _SCALE_EULER,  er / _SCALE_EULER,  ep / _SCALE_EULER,
            qw / _SCALE_QUAT,   qx / _SCALE_QUAT,   qy / _SCALE_QUAT,   qz / _SCALE_QUAT,
            ax / _SCALE_ACCEL,  ay / _SCALE_ACCEL,  az / _SCALE_ACCEL,
            gx / _SCALE_GYRO,   gy / _SCALE_GYRO,   gz / _SCALE_GYRO,
            vx / _SCALE_ACCEL,  vy / _SCALE_ACCEL,  vz / _SCALE_ACCEL,
            cs, cg, ca, cm,
        )
