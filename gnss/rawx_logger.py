#!/home/pi/aware-pi-logger/venv/bin/python
"""
UBX RAWX data logger for AWARE citizen-science network (station T010).
- RXM-RAWX / RXM-SFRBX → hourly binary .ubx files (→ upload → Darkside ZTD)
- NAV-PVT position → hourly device log .txt files (→ AWARE dashboard map)

Files are written to RAWX_DIR, rotated hourly, then moved to UPLOAD_DIR.
"""

import os
import sys
import signal
import shutil
import logging
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import serial
from pyubx2 import UBXReader, UBX_PROTOCOL

# ── Config ────────────────────────────────────────────────────────────────────

SCRIPT_DIR  = Path(__file__).resolve().parent.parent
CONFIG_FILE = SCRIPT_DIR / "config" / "config.env"


def load_config() -> dict:
    cfg: dict = {}
    if CONFIG_FILE.exists():
        for line in CONFIG_FILE.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                cfg[k.strip()] = v.strip()
    return cfg


cfg = load_config()

GNSS_DEVICE = cfg.get("GNSS_DEVICE", "/dev/ttyUSB0")
GNSS_BAUD   = int(cfg.get("GNSS_BAUD", 38400))
STATION_ID  = cfg.get("STATION_ID", "T000")
RAWX_DIR    = Path(cfg.get("RAWX_DIR",   SCRIPT_DIR / "data" / "rawx"))
UPLOAD_DIR  = Path(cfg.get("UPLOAD_DIR", SCRIPT_DIR / "data" / "upload_ready"))
LOG_DIR     = SCRIPT_DIR / "logs"

# Write a position entry to the device log every N seconds
POS_LOG_INTERVAL = 300

GPS_EPOCH     = datetime(1980, 1, 6, tzinfo=timezone.utc)
LEAP_SECONDS  = 18
MIN_VALID_UTC = datetime(2020, 1, 1, tzinfo=timezone.utc)

# ── Logging ───────────────────────────────────────────────────────────────────

LOG_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    filename=LOG_DIR / "rawx_logger.log",
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger(__name__)

# ── Signal handling ───────────────────────────────────────────────────────────

running = True


def handle_signal(sig, frame):
    global running
    running = False
    log.info("Shutdown signal %d received", sig)


signal.signal(signal.SIGTERM, handle_signal)
signal.signal(signal.SIGINT, handle_signal)

# ── Serial ────────────────────────────────────────────────────────────────────


def open_serial(max_retries: int = 10, delay: int = 5) -> serial.Serial:
    for attempt in range(1, max_retries + 1):
        try:
            ser = serial.Serial(GNSS_DEVICE, GNSS_BAUD, timeout=1)
            log.info("Serial opened: %s @ %d baud", GNSS_DEVICE, GNSS_BAUD)
            return ser
        except serial.SerialException as e:
            log.warning("Serial attempt %d/%d failed: %s", attempt, max_retries, e)
            time.sleep(delay)
    raise serial.SerialException(
        f"Cannot open {GNSS_DEVICE} after {max_retries} attempts"
    )

# ── File helpers ──────────────────────────────────────────────────────────────


def ubx_filename(dt: datetime) -> str:
    return f"{STATION_ID}_{dt.strftime('%Y%m%d_%H%M')}.ubx"


def log_filename(dt: datetime) -> str:
    return f"{STATION_ID}_log_{dt.strftime('%Y%m%d_%H%M')}.txt"


def log_line(level: str, msg: str) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    return f"{ts} [{level:5s}] {msg}\n"


def move_dir_to_upload() -> None:
    moved = 0
    for f in list(RAWX_DIR.iterdir()):
        if f.is_file():
            shutil.move(str(f), UPLOAD_DIR / f.name)
            moved += 1
            log.info("Moved to upload: %s", f.name)
    if moved:
        log.info("Moved %d file(s) to upload dir", moved)


def gps_to_utc(week: int, rcv_tow: float) -> "datetime | None":
    if week == 0:
        return None
    dt = GPS_EPOCH + timedelta(seconds=week * 604800 + rcv_tow - LEAP_SECONDS)
    return dt if dt >= MIN_VALID_UTC else None


def hour_start(dt: datetime) -> datetime:
    return dt.replace(minute=0, second=0, microsecond=0)

# ── Main ──────────────────────────────────────────────────────────────────────


def main() -> int:
    RAWX_DIR.mkdir(parents=True, exist_ok=True)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    # Move any files left over from a previous (crashed) run
    move_dir_to_upload()

    log.info("=== rawx_logger start: station=%s device=%s ===", STATION_ID, GNSS_DEVICE)

    ser = open_serial()
    reader = UBXReader(ser, protfilter=UBX_PROTOCOL)

    rawx_file  = None
    device_log = None
    cur_hour   = None    # datetime (hour-aligned UTC) of the currently open files
    last_pos_log = 0.0   # monotonic time of last position log write

    # ── Wait for GNSS lock ────────────────────────────────────────────────────
    log.info("Waiting for GNSS lock (NAV-PVT fixType >= 2)...")
    lock_sats = 0
    while running:
        try:
            raw_msg, parsed = reader.read()
        except Exception as e:
            log.warning("Read error (lock wait): %s", e)
            continue
        if parsed and parsed.identity == "NAV-PVT":
            ft = getattr(parsed, "fixType", 0)
            if ft >= 2:
                lock_sats = getattr(parsed, "numSV", 0)
                log.info("GNSS lock: fixType=%d  sats=%s", ft, lock_sats)
                break

    if not running:
        ser.close()
        return 0

    # ── Collection loop ───────────────────────────────────────────────────────
    while running:
        try:
            raw_msg, parsed = reader.read()
        except Exception as e:
            log.warning("Read error: %s", e)
            time.sleep(0.1)
            continue

        if not raw_msg or not parsed:
            continue

        now_utc = None

        # ── Derive UTC time ───────────────────────────────────────────────────
        ident = parsed.identity

        if ident == "NAV-PVT":
            try:
                now_utc = datetime(
                    parsed.year, parsed.month, parsed.day,
                    parsed.hour, parsed.min, parsed.second,
                    tzinfo=timezone.utc,
                )
            except Exception:
                pass

        elif ident in ("RXM-RAWX", "RXM-SFRBX"):
            try:
                now_utc = gps_to_utc(parsed.week, float(parsed.rcvTow))
            except Exception:
                pass

        # ── File rotation (on hour boundary) ─────────────────────────────────
        if now_utc:
            file_hour = hour_start(now_utc)
            if cur_hour is None or file_hour != cur_hour:
                # Close and ship existing files
                if cur_hour is not None:
                    for f in (rawx_file, device_log):
                        if f and not f.closed:
                            f.flush()
                            f.close()
                    move_dir_to_upload()

                # Open new files for this hour
                ubx_path = RAWX_DIR / ubx_filename(file_hour)
                dev_path = RAWX_DIR / log_filename(file_hour)
                rawx_file  = open(ubx_path, "ab")
                device_log = open(dev_path, "a", encoding="utf-8")
                cur_hour   = file_hour

                device_log.write(log_line("INFO", f"GNSS logger started, station={STATION_ID}"))
                if lock_sats:
                    device_log.write(log_line("INFO", f"GNSS lock active, sats={lock_sats}"))
                device_log.flush()
                log.info("Opened: %s  %s", ubx_path.name, dev_path.name)

        # ── Write RAWX/SFRBX to binary file ──────────────────────────────────
        if ident in ("RXM-RAWX", "RXM-SFRBX"):
            if rawx_file and not rawx_file.closed:
                rawx_file.write(raw_msg)
                rawx_file.flush()
                os.fsync(rawx_file.fileno())

        # ── Write position entry to device log ────────────────────────────────
        if ident == "NAV-PVT" and now_utc:
            ft = getattr(parsed, "fixType", 0)
            if ft >= 2:
                mono = time.monotonic()
                if mono - last_pos_log >= POS_LOG_INTERVAL:
                    last_pos_log = mono
                    lat    = parsed.lat            # degrees (auto-scaled by pyubx2)
                    lon    = parsed.lon            # degrees
                    height = int(parsed.hMSL // 1000)  # mm → m
                    nsv    = getattr(parsed, "numSV", 0)
                    if device_log and not device_log.closed:
                        device_log.write(log_line(
                            "INFO",
                            f"Position update: lat={lat:.7f}, lon={lon:.7f}, height={height} m"
                        ))
                        device_log.write(log_line("INFO", f"GNSS fix, sats={nsv}, fixType={ft}"))
                        device_log.flush()

    # ── Graceful shutdown ─────────────────────────────────────────────────────
    log.info("Shutdown: closing files and moving to upload dir...")
    for f in (rawx_file, device_log):
        if f and not f.closed:
            if hasattr(f, "mode") and "b" not in f.mode:
                f.write(log_line("INFO", "GNSS logger stopped"))
            f.flush()
            f.close()
    move_dir_to_upload()
    ser.close()
    log.info("=== rawx_logger stopped ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
