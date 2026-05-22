# ── I2C (BNO055) ──────────────────────────────────────────────────────────────
I2C_ID   = 0
I2C_SDA  = 0
I2C_SCL  = 1
I2C_FREQ = 400_000

BNO055_ADDR = 0x28

# ── SPI (SD card) ─────────────────────────────────────────────────────────────
SPI_ID   = 0
SPI_CLK  = 2
SPI_MOSI = 3
SPI_MISO = 4
SPI_CS   = 5
SPI_BAUD = 100_000      # 100 kHz — reliable with this level-shifter module

# ── Sampling ──────────────────────────────────────────────────────────────────
SAMPLE_RATE_HZ     = 50
SAMPLE_INTERVAL_MS = 1000 // SAMPLE_RATE_HZ   # 20 ms

# Rows buffered in RAM before flushing to SD (~1 s at 50 Hz)
BUFFER_SIZE = 50

# How often to write a health-summary line to the .log file (samples)
# 500 samples @ 50 Hz = every 10 seconds
LOG_INTERVAL_SAMPLES = 500

# ── Session ───────────────────────────────────────────────────────────────────
STARTUP_DELAY_S = 3     # Allow BNO055 to settle after power-on

# Filename prefixes (FAT32 8.3-compatible fallback when RTC date is default)
CSV_LONG_PREFIX     = "ski_"    # ski_YYYYMMDD_HHMMSS.csv
CSV_FALLBACK_PREFIX = "SKI_"    # SKI_001.CSV … SKI_999.CSV

# ── Timezone ──────────────────────────────────────────────────────────────────
# Offset added to RTC (which stores UTC) for the CSV datetime column.
# Set to 1 for CET (winter) or 2 for CEST (summer).
CET_OFFSET_H = 1
