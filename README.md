# aware-pi-logger

IoT GNSS data logger for Raspberry Pi (Debian Bookworm, arm64).  
Collects u-blox UBX RAWX binary data and uploads hourly to the [AWARE](https://aware-ethz.ch) citizen-science network (ETH Zurich).

## Hardware

| Component | Details |
|---|---|
| SBC | Raspberry Pi (arm64, Debian Bookworm) |
| GNSS | u-blox (USB CDC `/dev/ttyACM0` or GPIO UART `/dev/serial0`) |
| LTE Modem | Quectel EC25/EG-25 (USB-ID `2c7c:0125`, QMI interface) |
| SIM | Swisscom (APN `gprs.swisscom.ch`) |
| Tunnel | AutoSSH reverse tunnel → LuckyLuke (`192.33.89.14`) |

## What it does

Every hour the device produces two files and uploads them:

| File | Example | Destination |
|---|---|---|
| UBX binary | `T010_20260501_1200.ubx` | AWARE staging → Darkside SFTP (ZTD processing) |
| Device log | `T010_log_20260501_1200.txt` | AWARE dashboard (GPS map + alerts) |

Upload happens at :05 each hour. The AWARE server pipeline runs at :10.

## Quick start on a new Pi

```bash
# 1. Clone
git clone <repo-url> /home/pi/aware-pi-logger
cd /home/pi/aware-pi-logger

# 2. First run: copies config.env.example → config/config.env, then exits
sudo bash install.sh

# 3. Edit config — at minimum set these:
#    STATION_ID, TUNNEL_PORT, SSH_KEY, GNSS_DEVICE, AWARE_API_KEY
nano config/config.env

# 4. Copy SSH key for the reverse tunnel
scp user@luckyluke:~/.ssh/luckyluke ~/.ssh/luckyluke
chmod 600 ~/.ssh/luckyluke

# 5. Accept tunnel host key once (interactive)
ssh -i ~/.ssh/luckyluke pi@192.33.89.14 "echo ok"

# 6. Full install (creates venv, registers services and crontab)
sudo bash install.sh
```

## Configuration (`config/config.env`)

Copy `config/config.env.example` and fill in the values. **Never commit this file.**

| Variable | Example | Notes |
|---|---|---|
| `STATION_ID` | `T010` | Unique per device. T001–T999 = test, A001–A999 = production |
| `GNSS_DEVICE` | `/dev/ttyACM0` | u-blox USB CDC. GPIO UART = `/dev/serial0` |
| `GNSS_BAUD` | `38400` | Operating baud (after chip is configured) |
| `GNSS_INIT_BAUD` | `9600` | Factory default — used on first boot |
| `TUNNEL_PORT` | `2010` | Unique per device on LuckyLuke |
| `AWARE_API_KEY` | `...` | Obtain from ETH AWARE team |

## Directory layout

```
aware-pi-logger/
├── install.sh                  ← full setup for a fresh Pi
├── requirements.txt            ← Python dependencies
├── config/
│   ├── config.env.example      ← template (committed)
│   └── config.env              ← device secrets (git-ignored)
├── gnss/
│   ├── config_ublox.py         ← u-blox chip configuration (ExecStartPre)
│   ├── rawx_logger.py          ← RAWX recorder + device log writer
│   ├── uploader.py             ← hourly upload + error retry
│   ├── housekeeping.py         ← daily archive cleanup + disk check
│   └── logger.py               ← legacy NMEA→CSV logger (not active)
├── modem/
│   ├── start-qmi.sh            ← LTE connection via QMI
│   └── SETUP.md
├── tunnel/
│   ├── autossh.service.template
│   └── SETUP.md
├── data/                       ← git-ignored, created by install.sh
│   ├── rawx/                   ← files being written (current hour)
│   ├── upload_ready/           ← completed files awaiting upload
│   ├── archive/                ← successfully uploaded files
│   └── upload_error/           ← files that failed to upload
├── venv/                       ← Python venv (git-ignored)
└── logs/                       ← runtime logs (git-ignored)
```

## Services and autostart

| Mechanism | Script | Purpose |
|---|---|---|
| root `@reboot` crontab | `modem/start-qmi.sh` | LTE connection via QMI |
| systemd `ExecStartPre` | `gnss/config_ublox.py` | Configure u-blox chip (runs before logger, after 60 s boot delay) |
| systemd `gnss-logger.service` | `gnss/rawx_logger.py` | Collect RAWX data + write device log |
| root `cron 5 * * * *` | `gnss/uploader.py` | Upload to AWARE server (also retries from `upload_error/`) |
| root `cron 0 3 * * *` | `gnss/housekeeping.py` | Delete archives older than 7 days, check disk |
| systemd `autossh.service` | — | Reverse SSH tunnel to LuckyLuke |

## Multiple devices

Each Pi needs a unique `STATION_ID` and `TUNNEL_PORT` in `config/config.env`:

| Device | STATION_ID | TUNNEL_PORT |
|---|---|---|
| Ikarus-1 | T010 | 2010 |
| Ikarus-2 | T011 | 2011 |
| Ikarus-3 | T012 | 2012 |

## Logs and diagnostics

```bash
# GNSS RAWX logger (live)
sudo journalctl -u gnss-logger -f

# RAWX logger logfile
tail -f logs/rawx_logger.log

# u-blox chip configuration (runs once at boot)
cat logs/gnss_config.log

# Upload log
tail -f logs/uploader.log

# Check data directories
ls -lh data/rawx/ data/upload_ready/ data/archive/

# Tunnel
sudo systemctl status autossh

# Modem (after reboot)
cat logs/modem.log
ip addr show wwan0
```

## Known hardware quirks

- **ModemManager must be disabled** — it blocks `/dev/cdc-wdm0` (done by `install.sh`)
- **EC25 does not support WDA** — `--wda-get-data-format` always fails; `raw_ip=Y` is set manually
- **`raw_ip` resets on reboot** — `modem/start-qmi.sh` handles this via `@reboot` cron
- **`USER` is a reserved shell variable** — modem credentials use `MODEM_USER` / `MODEM_PASS`
- **RAWX requires baud ≥ 38400** — 9600 is too slow for 1 Hz raw measurements
- **u-blox USB CDC = `/dev/ttyACM0`** — Quectel modem occupies `ttyUSB0`–`ttyUSB3`; never confuse them
- **AWARE upload requires `device_id`** — POST body must include `data={"device_id": STATION_ID}` alongside the file
