#!/home/pi/aware-pi-logger/venv/bin/python
"""
One-shot u-blox chip configuration. Run once at @reboot before rawx_logger.py.
Enables RXM-RAWX, RXM-SFRBX, NAV-PVT on UART1. Saves to flash+BBR.
"""

import serial
import time
import logging
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent.parent
CONFIG_FILE = SCRIPT_DIR / "config" / "config.env"
LOG_DIR = SCRIPT_DIR / "logs"


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
GNSS_DEVICE    = cfg.get("GNSS_DEVICE", "/dev/ttyUSB0")
GNSS_BAUD      = int(cfg.get("GNSS_BAUD", 38400))
GNSS_INIT_BAUD = int(cfg.get("GNSS_INIT_BAUD", 9600))

LOG_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    filename=LOG_DIR / "gnss_config.log",
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger(__name__)

# Raw UBX commands (checksums pre-verified against Altprojekt + hand-computed)
# CFG-PRT: UART1 → 38400 baud, in=UBX, out=UBX
CMD_CFG_PRT = (
    b'\xB5\x62\x06\x00\x14\x00\x01\x00\x00\x00'
    b'\xD0\x08\x00\x00\x00\x96\x00\x00\x01\x00'
    b'\x01\x00\x00\x00\x00\x00\x8B\x54'
)
# CFG-MSG: enable RXM-RAWX (0x02/0x15) on UART1 + USB
CMD_RAWX   = b'\xB5\x62\x06\x01\x08\x00\x02\x15\x00\x01\x00\x01\x00\x00\x28\x4E'
# CFG-MSG: enable RXM-SFRBX (0x02/0x13) on UART1 + USB
CMD_SFRBX  = b'\xB5\x62\x06\x01\x08\x00\x02\x13\x00\x01\x00\x01\x00\x00\x26\x40'
# CFG-MSG: enable NAV-PVT (0x01/0x07) on UART1 + USB
CMD_NAVPVT = b'\xB5\x62\x06\x01\x08\x00\x01\x07\x00\x01\x00\x01\x00\x00\x19\xE4'
# CFG-CFG: save all to flash + BBR (deviceMask=0x17)
CMD_SAVE   = (
    b'\xB5\x62\x06\x09\x0D\x00\x00\x00\x00\x00'
    b'\xFF\xFF\xFF\xFF\x00\x00\x00\x00\x17\x2F\xB2'
)

COMMANDS = [
    (CMD_CFG_PRT,  "CFG-PRT  baud→38400 UBX only"),
    (CMD_RAWX,     "CFG-MSG  RXM-RAWX enable"),
    (CMD_SFRBX,    "CFG-MSG  RXM-SFRBX enable"),
    (CMD_NAVPVT,   "CFG-MSG  NAV-PVT enable"),
    (CMD_SAVE,     "CFG-CFG  save flash+BBR"),
]


def send_command(ser: serial.Serial, cmd: bytes, desc: str) -> None:
    ser.write(cmd)
    log.info("Sent %-35s  %s", desc, cmd.hex())
    time.sleep(0.5)
    resp = ser.read(ser.in_waiting or 1)
    if resp:
        log.info("Response %-30s  %s", desc, resp.hex())
    else:
        log.warning("No response for %s", desc)


def main() -> int:
    log.info("=== u-blox config start ===")
    log.info("Device: %s  target baud: %d  init baud: %d",
             GNSS_DEVICE, GNSS_BAUD, GNSS_INIT_BAUD)

    ser = None
    # Try target baud first (device already configured), fall back to factory default
    for baud in (GNSS_BAUD, GNSS_INIT_BAUD):
        try:
            s = serial.Serial(GNSS_DEVICE, baud, timeout=1)
            s.flushInput()
            time.sleep(0.3)
            probe = s.read(s.in_waiting or 1)
            log.info("Opened at %d baud (probe: %d bytes)", baud, len(probe))
            ser = s
            break
        except serial.SerialException as e:
            log.warning("Open at %d baud failed: %s", baud, e)

    if ser is None:
        log.error("Cannot open %s at any baud rate", GNSS_DEVICE)
        return 1

    try:
        for cmd, desc in COMMANDS:
            send_command(ser, cmd, desc)
        log.info("All commands sent")
    except Exception as e:
        log.error("Config error: %s", e)
        return 1
    finally:
        ser.close()
        log.info("=== u-blox config done ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
