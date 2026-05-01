#!/usr/bin/env python3
"""
u-blox GNSS data logger.
Reads NMEA sentences from serial port and writes timestamped records to CSV.

Device and baud rate are read from config/config.env (see config.env.example).
"""

import os
import sys
import csv
import time
import signal
import serial
from datetime import datetime, timezone
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────

SCRIPT_DIR = Path(__file__).resolve().parent.parent
CONFIG_FILE = SCRIPT_DIR / "config" / "config.env"

def load_config():
    cfg = {}
    if CONFIG_FILE.exists():
        for line in CONFIG_FILE.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                cfg[k.strip()] = v.strip()
    return cfg

cfg = load_config()

GNSS_DEVICE   = cfg.get("GNSS_DEVICE", "/dev/ttyUSB0")
GNSS_BAUD     = int(cfg.get("GNSS_BAUD", 9600))
LOG_DIR       = Path(cfg.get("LOG_DIR", SCRIPT_DIR / "logs"))
LOG_INTERVAL  = int(cfg.get("LOG_INTERVAL_SEC", 1))

# ── Signal handling ───────────────────────────────────────────────────────────

running = True

def handle_signal(sig, frame):
    global running
    print("\n[logger] Shutting down...")
    running = False

signal.signal(signal.SIGINT, handle_signal)
signal.signal(signal.SIGTERM, handle_signal)

# ── NMEA helpers ──────────────────────────────────────────────────────────────

def parse_gga(sentence):
    """Parse GGA sentence. Returns dict or None on failure."""
    try:
        parts = sentence.split(",")
        if len(parts) < 10 or parts[0] not in ("$GPGGA", "$GNGGA"):
            return None
        if not parts[2] or not parts[4]:
            return None  # no fix

        def nmea_coord(raw, hemi):
            deg = int(float(raw) / 100)
            minutes = float(raw) - deg * 100
            val = deg + minutes / 60
            return -val if hemi in ("S", "W") else val

        return {
            "utc_time":  parts[1],
            "lat":       nmea_coord(parts[2], parts[3]),
            "lon":       nmea_coord(parts[4], parts[5]),
            "fix":       int(parts[6]),
            "satellites": int(parts[7]),
            "hdop":      float(parts[8]) if parts[8] else None,
            "altitude_m": float(parts[9]) if parts[9] else None,
        }
    except (ValueError, IndexError):
        return None

# ── Main loop ─────────────────────────────────────────────────────────────────

def main():
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_file = LOG_DIR / f"gnss_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"

    print(f"[logger] Device : {GNSS_DEVICE} @ {GNSS_BAUD} baud")
    print(f"[logger] Log    : {log_file}")

    try:
        port = serial.Serial(GNSS_DEVICE, GNSS_BAUD, timeout=2)
    except serial.SerialException as e:
        print(f"[logger] ERROR: Cannot open {GNSS_DEVICE}: {e}", file=sys.stderr)
        sys.exit(1)

    fields = ["timestamp_utc", "lat", "lon", "fix", "satellites", "hdop", "altitude_m"]

    with open(log_file, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()

        last_write = 0.0

        while running:
            try:
                raw = port.readline().decode("ascii", errors="replace").strip()
            except serial.SerialException as e:
                print(f"[logger] Serial error: {e}", file=sys.stderr)
                time.sleep(1)
                continue

            fix = parse_gga(raw)
            if fix is None:
                continue

            now = time.monotonic()
            if now - last_write < LOG_INTERVAL:
                continue
            last_write = now

            row = {"timestamp_utc": datetime.now(timezone.utc).isoformat(), **fix}
            writer.writerow(row)
            f.flush()
            print(f"[logger] {row['timestamp_utc']}  lat={row['lat']:.6f}  lon={row['lon']:.6f}  "
                  f"sats={row['satellites']}  alt={row['altitude_m']}m")

    port.close()
    print("[logger] Done.")

if __name__ == "__main__":
    main()
