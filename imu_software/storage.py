import os

_SD_MOUNT       = "/sd"
_MIN_SD_FREE_MB = 50       # halt if SD card has less than this free
_WARN_SD_FREE_MB = 200     # print a warning below this threshold


def _statvfs_mb(path):
    """Return (total_mb, free_mb) for the filesystem at path, or (0, 0) on error."""
    try:
        s = os.statvfs(path)  # type: ignore[attr-defined]
        block = s[0]
        total = block * s[2]
        free  = block * s[3]
        return total // (1024 * 1024), free // (1024 * 1024)
    except Exception:
        return 0, 0


def _list_flash():
    """Return all files on internal flash recursively."""
    files = []
    def _walk(path):
        try:
            for entry in os.listdir(path):  # type: ignore[attr-defined]
                full = path + "/" + entry if path != "/" else "/" + entry
                try:
                    os.listdir(full)   # type: ignore[attr-defined]
                    _walk(full)
                except OSError:
                    files.append(full)
        except Exception:
            pass
    _walk("/")
    return files


def report():
    """
    Print a storage report for both internal flash and SD card.
    Returns True if SD card is mounted and has enough space, False otherwise.
    """
    print()
    print("── Storage report ───────────────────────────────────")

    # ── Internal flash ────────────────────────────────────────────────────
    total_mb, free_mb = _statvfs_mb("/")
    used_mb = total_mb - free_mb
    print("  Internal flash : {}/{} KB used".format(used_mb * 1024, total_mb * 1024))

    flash_files = _list_flash()
    if flash_files:
        print("  Files on flash :")
        for f in flash_files:
            print("    {}".format(f))
        # Flag any data files that should not be on internal flash
        data_files = [f for f in flash_files if f.upper().endswith((".CSV", ".TXT", ".LOG"))]
        if data_files:
            print("  !! WARNING: data files found on internal flash — delete them!")
            for f in data_files:
                print("     {}".format(f))
    else:
        print("  Files on flash : (none)")

    # ── SD card ───────────────────────────────────────────────────────────
    sd_total, sd_free = _statvfs_mb(_SD_MOUNT)
    if sd_total == 0:
        print("  SD card        : NOT MOUNTED")
        print("─────────────────────────────────────────────────────")
        return False

    pct_used = 100 * (sd_total - sd_free) // sd_total if sd_total else 0
    print("  SD card        : {} MB free / {} MB total  ({}% used)".format(
        sd_free, sd_total, pct_used))

    if sd_free < _MIN_SD_FREE_MB:
        print("  !! CRITICAL: SD card almost full — logging halted to protect data")
        print("─────────────────────────────────────────────────────")
        return False

    if sd_free < _WARN_SD_FREE_MB:
        print("  !! WARNING: SD card below {} MB free".format(_WARN_SD_FREE_MB))

    print("─────────────────────────────────────────────────────")
    return True


def guard_path(path):
    """
    Raise RuntimeError if path is not on the SD card.
    Call before every open() to prevent accidental writes to internal flash.
    """
    if not path.startswith(_SD_MOUNT + "/"):
        raise RuntimeError(
            "BLOCKED: path '{}' is not on SD card. "
            "All data files must start with {}/".format(path, _SD_MOUNT)
        )


def sd_free_mb():
    """Return current free MB on SD card."""
    _, free = _statvfs_mb(_SD_MOUNT)
    return free
