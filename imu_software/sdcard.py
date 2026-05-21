"""
sdcard.py — MicroPython SPI SD card block device driver.

Source: micropython/micropython-lib (MIT licence, Damien P. George et al.)
Included here so the firmware is fully self-contained — copy this file to
the RP2350 filesystem alongside the other .py files.

Usage:
    import sdcard, machine, uos
    spi = machine.SPI(0, ...)
    cs  = machine.Pin(17, machine.Pin.OUT, value=1)
    sd  = sdcard.SDCard(spi, cs)
    uos.mount(sd, "/sd")
"""

from micropython import const
import time

_CMD_TIMEOUT      = const(1500)   # R1 response: fast, a few bytes
_DATA_TIMEOUT     = const(60000)  # data token: 60000 × 20 µs @ 400 kHz ≈ 1.2 s; slow cards need this
_R1_IDLE_STATE    = const(1 << 0)
_R1_ILLEGAL_CMD   = const(1 << 2)
_TOKEN_CMD25      = const(0xFC)
_TOKEN_STOP_TRAN  = const(0xFD)
_TOKEN_DATA       = const(0xFE)


class SDCard:
    def __init__(self, spi, cs, baudrate=1_000_000):
        self.spi = spi
        self.cs  = cs

        self.cmdbuf  = bytearray(6)
        self.dummybuf = bytearray(512)
        self.tokenbuf = bytearray(1)
        for i in range(512):
            self.dummybuf[i] = 0xFF
        self._dmv = memoryview(self.dummybuf)

        self.cs.init(self.cs.OUT, value=1)

        # Low-speed init phase
        self.spi.init(baudrate=baudrate, phase=0, polarity=0)
        self._baudrate = baudrate

        # Clock card ≥ 74 cycles with CS deasserted
        for _ in range(80):
            self.spi.write(b"\xff")
        time.sleep(5)

        # CMD0 — software reset (expect R1 = 0x01 IDLE)
        # Print every response for the first 5 attempts so we can see what
        # the card (or floating MISO) is actually sending back.
        # -1  → timeout: card never drove MISO low  (wiring or CS problem)
        # 0x00 → MISO floating low OR card in transfer state
        # 0x01 → correct IDLE response, card in SPI mode
        print("  SD CMD0 responses (expect 0x01):")
        for attempt in range(20):
            r = self._cmd(0, 0, 0x95)
            if attempt < 5:
                print("    attempt {}: 0x{:02x}".format(attempt, r & 0xFF))
            if r == _R1_IDLE_STATE:
                print("  SD CMD0 OK — card in SPI mode")
                break
            if r == 0x00:
                print("  SD CMD0: 0x00 — MISO may be floating low (no pull-up)")
                break
        else:
            raise OSError("no SD card")

        # CMD8 — determine card version (v1 vs v2)
        r = self._cmd(8, 0x01AA, 0x87, final=4)
        if r == _R1_IDLE_STATE or r == 0x00:
            self._init_v2()
        elif r == (_R1_IDLE_STATE | _R1_ILLEGAL_CMD):
            self._init_v1()
        else:
            raise OSError("SD: unknown card version (CMD8 response 0x{:02x})".format(r))

        # CMD9 — read CSD to get card capacity
        if self._cmd(9, 0, 0, final=0, release=False) != 0:
            raise OSError("SD: CMD9 failed")
        csd = bytearray(16)
        self._readinto(csd)
        if csd[0] & 0xC0 == 0x40:          # CSD v2 (SDHC/SDXC)
            self.sectors = ((csd[8] << 8 | csd[9]) + 1) * 1024
        elif csd[0] & 0xC0 == 0x00:        # CSD v1 (≤2 GB)
            c_size      = (csd[6] & 0x03) << 10 | csd[7] << 2 | csd[8] >> 6
            c_size_mult = (csd[9]  & 0x03) << 1  | csd[10] >> 7
            bl_len      =  csd[5]  & 0x0F
            self.sectors = (c_size + 1) * (2 ** (c_size_mult + 2)) * (2 ** bl_len) // 512
        else:
            raise OSError("SD: unsupported CSD format")

        # CMD16 — fix block length to 512 bytes
        # SDHC/SDXC cards (cdv=1) have a fixed 512-byte block size by spec;
        # sending CMD16 is a no-op but some cards enter an internal state that
        # delays the first CMD17 data response. Skip it for SDHC.
        if self.cdv != 1:
            if self._cmd(16, 512, 0) != 0:
                raise OSError("SD: CMD16 failed")

        # Let the card settle after init before the first data command.
        time.sleep(0.1)

    # ── Card initialisation helpers ───────────────────────────────────────

    def _init_v1(self):
        for _ in range(_CMD_TIMEOUT):
            self._cmd(55, 0, 0)
            if self._cmd(41, 0, 0) == 0:
                self.cdv = 512
                return
        raise OSError("SD: v1 init timeout")

    def _init_v2(self):
        # Try HCS=1 (SDHC/SDXC) first, then HCS=0 (SDSC) as fallback.
        # Some modules need > 5 s from cold power-on, so budget 5 s per variant.
        for hcs_arg in (0x40000000, 0x00000000):
            print("  ACMD41 loop HCS={} (0x{:08x})".format(1 if hcs_arg else 0, hcs_arg))
            for i in range(100):    # 100 × 50 ms = 5 s
                r55 = self._cmd(55, 0, 0)
                r41 = self._cmd(41, hcs_arg, 0)
                if i < 5:
                    print("    [{}] CMD55=0x{:02x}  ACMD41=0x{:02x}".format(
                        i, r55 & 0xFF, r41 & 0xFF))
                if r41 == 0:
                    # Read OCR (CMD58) to get CCS bit and determine addressing mode
                    r58 = self._cmd(58, 0, 0, release=False)
                    ocr = bytearray(4)
                    self.spi.readinto(ocr, 0xFF)
                    self.cs(1)
                    self.spi.write(b"\xff")
                    # CCS bit (OCR bit 30 = ocr[0] bit 6): 1→SDHC block addr, 0→SDSC byte addr
                    self.cdv = 1 if (r58 == 0 and (ocr[0] & 0x40)) else 512
                    print("  CMD58 OCR: {:02x}{:02x}{:02x}{:02x}  cdv={} r58=0x{:02x}".format(
                        ocr[0], ocr[1], ocr[2], ocr[3], self.cdv, r58 & 0xFF))
                    return
                time.sleep(0.05)
        raise OSError("SD: v2 init timeout")
    
    # ── Low-level SPI primitives ──────────────────────────────────────────

    def _cmd(self, cmd, arg, crc, final=0, release=True, skip1=False):
        self.cs(0)
        b = self.cmdbuf
        b[0] = 0x40 | cmd
        b[1] = arg >> 24
        b[2] = arg >> 16
        b[3] = arg >> 8
        b[4] = arg
        b[5] = crc | 0x01  # end bit must always be 1 per SD spec
        self.spi.write(b)

        if skip1:
            self.spi.readinto(self.tokenbuf, 0xFF)

        for _ in range(_CMD_TIMEOUT):
            self.spi.readinto(self.tokenbuf, 0xFF)
            resp = self.tokenbuf[0]
            if not (resp & 0x80):
                for _ in range(final):
                    self.spi.write(b"\xff")
                if release:
                    self.cs(1)
                    self.spi.write(b"\xff")
                return resp

        self.cs(1)
        self.spi.write(b"\xff")
        return -1   # timeout

    def _readinto(self, buf):
        self.cs(0)
        count = 0
        for _ in range(_DATA_TIMEOUT):
            self.spi.readinto(self.tokenbuf, 0xFF)
            count += 1
            if count <= 10:
                print("  readinto byte {}: 0x{:02x}".format(count, self.tokenbuf[0]))
            if self.tokenbuf[0] == _TOKEN_DATA:
                print("  ✓ Got data token at byte {}".format(count))
                break
        else:
            self.cs(1)
            print("_readinto: no 0xFE after {} bytes, last=0x{:02x}".format(
                count, self.tokenbuf[0]))
            raise OSError("SD: read data timeout")

        if len(buf) == 512:
            self.spi.write_readinto(self._dmv, buf)
        else:
            # Read exactly len(buf) bytes — do NOT over-clock with a 512-byte read,
            # as excess clocks with CS held low can corrupt the card's state machine.
            tmp = bytearray(len(buf))
            self.spi.readinto(tmp, 0xFF)
            for i in range(len(buf)):
                buf[i] = tmp[i]

        self.spi.write(b"\xff\xff")   # discard 2 CRC bytes
        self.cs(1)
        self.spi.write(b"\xff")

    def _write_block(self, token, buf):
        self.cs(0)
        self.spi.write(b"\xff")
        self.spi.write(bytes([token]))
        self.spi.write(buf)
        self.spi.write(b"\xff\xff")   # dummy CRC
        # Read up to 16 bytes for the data-response token — some cards send
        # one or two 0xFF idle bytes before the token (bit pattern x x x 0 S S S 1).
        resp = 0xFF
        for _ in range(16):
            resp = self.spi.read(1, 0xFF)[0]
            if resp != 0xFF:
                break
        if (resp & 0x1F) != 0x05:
            self.cs(1)
            raise OSError("SD: write rejected (resp=0x{:02x})".format(resp))
        while self.spi.read(1, 0xFF)[0] == 0:
            pass                      # wait for card to finish programming
        self.cs(1)
        self.spi.write(b"\xff")

    # ── Block device interface (required by uos.mount) ────────────────────

    def readblocks(self, block_num, buf, offset=None):
        # 8 idle clocks with CS high so the card sees a clean gap before CMD17/18
        self.cs(1)
        self.spi.write(b"\xff")
        nblocks = len(buf) // 512
        print("  readblocks: block={} nblocks={} cdv={}".format(block_num, nblocks, self.cdv))
        assert nblocks and not len(buf) % 512
        if nblocks == 1:
            r = self._cmd(17, block_num * self.cdv, 0, release=False)
            print("  CMD17 addr={} r1=0x{:02x}".format(block_num * self.cdv, r & 0xFF))
            if r != 0:
                self.cs(1)
                raise OSError("SD: CMD17 read error")
            self._readinto(buf)
        else:
            r = self._cmd(18, block_num * self.cdv, 0, release=False)
            print("  CMD18 addr={} r1=0x{:02x}".format(block_num * self.cdv, r & 0xFF))
            if r != 0:
                self.cs(1)
                raise OSError("SD: CMD18 read error")
            mv, off = memoryview(buf), 0
            while nblocks:
                self._readinto(mv[off:off + 512])
                off += 512
                nblocks -= 1
            if self._cmd(12, 0, 0xFF, skip1=True) != 0:
                raise OSError("SD: CMD12 stop error")

    def writeblocks(self, block_num, buf, offset=None):
        nblocks = len(buf) // 512
        assert nblocks and not len(buf) % 512
        if nblocks == 1:
            # release=False keeps CS LOW through _write_block; a CS pulse
            # between CMD24 and the data packet confuses some cards.
            if self._cmd(24, block_num * self.cdv, 0, release=False) != 0:
                self.cs(1)
                raise OSError("SD: CMD24 write error")
            self._write_block(_TOKEN_DATA, buf)
        else:
            if self._cmd(25, block_num * self.cdv, 0, release=False) != 0:
                self.cs(1)
                raise OSError("SD: CMD25 write error")
            mv, off = memoryview(buf), 0
            while nblocks:
                self.spi.write(b"\xff")
                self.spi.write(bytes([_TOKEN_CMD25]))
                self.spi.write(mv[off:off + 512])
                self.spi.write(b"\xff\xff")
                resp = self.spi.read(1, 0xFF)[0]
                if (resp & 0x1F) != 0x05:
                    self.cs(1)
                    raise OSError("SD: multi-write rejected")
                while self.spi.read(1, 0xFF)[0] == 0:
                    pass
                off += 512
                nblocks -= 1
            self.spi.write(bytes([_TOKEN_STOP_TRAN]))
            self.cs(1)
            self.spi.write(b"\xff")

    def ioctl(self, op, arg):
        if op == 4:   # BLOCK_COUNT
            return self.sectors
        if op == 5:   # BLOCK_SIZE
            return 512
        if op == 6:   # ERASE_BLOCK
            return 0
