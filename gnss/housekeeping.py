#!/home/pi/aware-pi-logger/venv/bin/python
"""
Daily housekeeping: remove old archived files to prevent disk fill-up.
Run via cron once per day.
"""

import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

SCRIPT_DIR  = Path(__file__).resolve().parent.parent
CONFIG_FILE = SCRIPT_DIR / "config" / "config.env"
LOG_DIR     = SCRIPT_DIR / "logs"

ARCHIVE_MAX_DAYS = 7   # keep last N days in archive
ERROR_MAX_DAYS   = 30  # keep error files longer for manual inspection


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
ARCHIVE_DIR = Path(cfg.get("ARCHIVE_DIR", SCRIPT_DIR / "data" / "archive"))
ERROR_DIR   = Path(cfg.get("ERROR_DIR",   SCRIPT_DIR / "data" / "upload_error"))

LOG_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    filename=LOG_DIR / "housekeeping.log",
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger(__name__)


def purge_old_files(directory: Path, max_age_days: int) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    removed = 0
    for f in directory.iterdir():
        if not f.is_file():
            continue
        mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)
        if mtime < cutoff:
            f.unlink()
            log.info("Deleted %s (age: %dd)", f.name, (datetime.now(timezone.utc) - mtime).days)
            removed += 1
    return removed


def main() -> int:
    log.info("=== housekeeping start ===")

    n_archive = purge_old_files(ARCHIVE_DIR, ARCHIVE_MAX_DAYS) if ARCHIVE_DIR.exists() else 0
    n_error   = purge_old_files(ERROR_DIR,   ERROR_MAX_DAYS)   if ERROR_DIR.exists()   else 0

    # Log disk usage after cleanup
    import shutil as _shutil
    total, used, free = _shutil.disk_usage("/")
    pct = used / total * 100
    log.info(
        "Disk: %.1f GB used / %.1f GB total (%.0f%%)  |  "
        "Deleted: %d archive  %d error",
        used / 1e9, total / 1e9, pct, n_archive, n_error,
    )
    if pct > 85:
        log.warning("Disk usage above 85%% — consider reducing ARCHIVE_MAX_DAYS")

    log.info("=== housekeeping done ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
