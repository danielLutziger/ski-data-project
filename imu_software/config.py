"""
config.py — Hardware pin assignments and tunable constants.

Wiring:
  BNO055 → RP2350-Zero (I2C0)
    SDA → GP4 | SCL → GP5 | VIN → 3.3V | GND → GND

  WeMos SD Shield → RP2350-Zero (SPI0)
    D5/CLK  → GP18 | D6/MISO → GP16 | D7/MOSI → GP19 | D4/CS → GP17
    3V3 → 3V3 | G → GND

  Status LED
    External: anode → GP15, cathode → GND via 330Ω resistor.

  ⚠ NOTE: The Waveshare RP2350-Zero onboard WS2812B RGB LED is wired
     to GP16 on the PCB. GP16 is also used here for SPI MISO.
     These cannot share the pin safely. Use an external LED on GP15
     (recommended), OR rewire MISO to GP12 if you want the onboard LED.
"""

# ── I2C (BNO055) ──────────────────────────────────────────────────────────
I2C_ID   = 0
I2C_SDA  = 0
I2C_SCL  = 1
I2C_FREQ = 400_000          # 400 kHz fast-mode

BNO055_ADDR = 0x28          # 0x29 if ADR pin is pulled high

# ── SPI (SD card) ─────────────────────────────────────────────────────────
SPI_ID   = 0
SPI_MISO = 4
SPI_MOSI = 3
SPI_CLK  = 2
SPI_CS   = 5
SPI_BAUD = 10_000_000       # 10 MHz; drop to 1_000_000 if card errors appear

# ── LED ───────────────────────────────────────────────────────────────────
#LED_PIN  = 15               # External simple GPIO LED

# ── Sampling ──────────────────────────────────────────────────────────────
SAMPLE_RATE_HZ     = 50
SAMPLE_INTERVAL_MS = 1000 // SAMPLE_RATE_HZ   # 20 ms

# Samples to accumulate before flushing to SD (~1 s at 50 Hz)
BUFFER_SIZE = 50

# ── Session ───────────────────────────────────────────────────────────────
STARTUP_DELAY_S = 3         # Allow BNO055 to power-on and settle

# Filename templates (FAT32 8.3 fallback used when no RTC is available)
CSV_LONG_PREFIX     = "ski_"        # ski_YYYYMMDD_HHMMSS.csv
CSV_FALLBACK_PREFIX = "SKI_"        # SKI_001.CSV … SKI_999.CSV
