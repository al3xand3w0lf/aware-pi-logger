#!/home/pi/aware-pi-logger/venv/bin/python
"""
Upload completed RAWX .ubx and device log .txt files to AWARE server.
Run via cron at :05 each hour.
"""

import shutil
import logging
import time
from pathlib import Path

import requests

SCRIPT_DIR  = Path(__file__).resolve().parent.parent
CONFIG_FILE = SCRIPT_DIR / "config" / "config.env"
LOG_DIR     = SCRIPT_DIR / "logs"


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
STATION_ID    = cfg.get("STATION_ID",    "T000")
UPLOAD_DIR    = Path(cfg.get("UPLOAD_DIR",   SCRIPT_DIR / "data" / "upload_ready"))
ARCHIVE_DIR   = Path(cfg.get("ARCHIVE_DIR",  SCRIPT_DIR / "data" / "archive"))
ERROR_DIR     = Path(cfg.get("ERROR_DIR",    SCRIPT_DIR / "data" / "upload_error"))
AWARE_API_URL = cfg.get("AWARE_API_URL", "")
AWARE_API_KEY = cfg.get("AWARE_API_KEY", "")

LOG_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    filename=LOG_DIR / "uploader.log",
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger(__name__)

RETRY_DELAYS = [30, 60, 120]  # seconds between upload attempts


def upload_file(fpath: Path) -> bool:
    fname = fpath.name
    for attempt, delay in enumerate(RETRY_DELAYS, 1):
        try:
            with open(fpath, "rb") as f:
                resp = requests.post(
                    AWARE_API_URL,
                    headers={"X-API-Key": AWARE_API_KEY},
                    files={"file": (fname, f)},
                    timeout=60,
                )
            if resp.status_code == 201:
                log.info("OK %s (HTTP 201)", fname)
                return True
            if 400 <= resp.status_code < 500:
                # Client error — no point retrying
                log.error("Permanent failure %s: HTTP %d %s", fname, resp.status_code, resp.text[:200])
                return False
            # 5xx or unexpected — retry
            log.warning("Attempt %d/%d for %s: HTTP %d, retry in %ds",
                        attempt, len(RETRY_DELAYS), fname, resp.status_code, delay)
        except requests.RequestException as e:
            log.warning("Attempt %d/%d for %s: %s, retry in %ds",
                        attempt, len(RETRY_DELAYS), fname, e, delay)
        if attempt < len(RETRY_DELAYS):
            time.sleep(delay)

    log.error("All attempts exhausted for %s", fname)
    return False


def main() -> int:
    for d in (ARCHIVE_DIR, ERROR_DIR):
        d.mkdir(parents=True, exist_ok=True)

    if not AWARE_API_URL or not AWARE_API_KEY or AWARE_API_KEY == "your_api_key_here":
        log.error("AWARE_API_URL or AWARE_API_KEY not configured in config.env")
        return 1

    # Device logs first (lighter, server sees station before big UBX arrives)
    files = (
        sorted(UPLOAD_DIR.glob(f"{STATION_ID}_log_*.txt"))
        + sorted(UPLOAD_DIR.glob(f"{STATION_ID}_*.ubx"))
    )

    if not files:
        log.info("Nothing to upload")
        return 0

    log.info("=== uploader start: %d file(s) ===", len(files))
    ok = err = 0
    for fpath in files:
        dest = ARCHIVE_DIR if upload_file(fpath) else ERROR_DIR
        shutil.move(str(fpath), dest / fpath.name)
        if dest == ARCHIVE_DIR:
            ok += 1
        else:
            err += 1

    log.info("=== uploader done: %d ok  %d failed ===", ok, err)
    return 0 if err == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
