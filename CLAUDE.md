# aware-pi-logger – Kontext für Claude

## Projektübersicht

IoT GNSS-Datenlogger auf Raspberry Pi (arm64, Debian Bookworm) für das [AWARE](https://aware-ethz.ch) Citizen-Science-Netzwerk (ETH Zürich).  
Gerätename: **Ikarus**. Jedes Gerät ist eine eigene Instanz dieses Repos mit eigener `config/config.env`.

## Hardware

| Komponente | Details |
|---|---|
| SBC | Raspberry Pi (arm64, Debian Bookworm) |
| GNSS | u-blox (USB oder GPIO-UART `/dev/serial0`) |
| LTE-Modem | Quectel EC25 / EG-25 (USB-ID `2c7c:0125`) |
| QMI-Device | `/dev/cdc-wdm0` |
| Netzwerk-Interface | `wwan0` |
| SIM | Swisscom (APN `gprs.swisscom.ch`) |

## Wichtige Eigenheiten

- **ModemManager ist deaktiviert** – nie wieder aktivieren, er blockiert `/dev/cdc-wdm0`.
- **`--wda-get-data-format` schlägt immer fehl** – EC25 unterstützt WDA nicht, `raw_ip=Y` manuell setzen reicht.
- **raw_ip muss bei jedem Boot gesetzt werden** – erledigt `modem/start-qmi.sh`.
- **`USER` ist eine reservierte Shell-Variable** – Modem-Credentials heissen `MODEM_USER` / `MODEM_PASS`.
- **RAWX benötigt ≥ 38400 Baud** – bei 9600 ist der Bus zu langsam für 1-Hz-Rohdaten.

## Python-Umgebung

Alle Python-Scripts laufen im venv unter `venv/` (git-ignoriert).  
Interpreter: `/home/pi/aware-pi-logger/venv/bin/python`  
Pakete: `pyubx2`, `requests`, `pyserial` — siehe `requirements.txt`.  
Venv wird von `install.sh` automatisch erstellt und befüllt.

## Services & Autostart

| Mechanismus | Datei | Zweck | Timing |
|---|---|---|---|
| root `@reboot` crontab | `modem/start-qmi.sh` | LTE-Verbindung via QMI | Boot + 0 s |
| root `@reboot` crontab | `gnss/config_ublox.py` | u-blox Chip konfigurieren | Boot + 45 s |
| systemd `gnss-logger.service` | `gnss/rawx_logger.py` | RAWX aufzeichnen + Device-Log schreiben | kontinuierlich |
| root `cron 5 * * * *` | `gnss/uploader.py` | Upload zu AWARE-Server | jede Stunde :05 |
| systemd `autossh.service` | — | Reverse-SSH-Tunnel → LuckyLuke | kontinuierlich |

## Konfiguration

Alle gerätespezifischen Werte stehen in `config/config.env` (nicht im Repo).  
Vorlage: `config/config.env.example`.

Wichtigste Variablen (pro Gerät eindeutig):

| Variable | Beispiel | Hinweis |
|---|---|---|
| `STATION_ID` | `T010` | T001–T999 = Test, A001–A999 = Produktion |
| `TUNNEL_PORT` | `2010` | Eindeutig pro Gerät auf LuckyLuke |
| `GNSS_DEVICE` | `/dev/ttyUSB0` | Oder `/dev/serial0` für GPIO-UART |
| `GNSS_BAUD` | `38400` | Nach einmaliger Chip-Konfiguration |
| `GNSS_INIT_BAUD` | `9600` | Werkseinstellung, nur für config_ublox.py |
| `AWARE_API_KEY` | `...` | Von ETH AWARE-Team anfordern |

## GNSS-Pipeline

```
u-blox Chip
  ↓  serial (38400 baud)
gnss/config_ublox.py   (einmalig @reboot: aktiviert RAWX, SFRBX, NAV-PVT)
  ↓
gnss/rawx_logger.py    (systemd, Endlosschleife)
  ├── RXM-RAWX/SFRBX  → data/rawx/T010_YYYYMMDD_HHMM.ubx  (binary append + fsync)
  └── NAV-PVT         → data/rawx/T010_log_YYYYMMDD_HHMM.txt  (GPS-Position für Dashboard)
        ↓  Stundenwechsel: Dateien → data/upload_ready/
gnss/uploader.py       (cron :05)
  └── POST https://aware-ethz.ch/upload  (X-API-Key, multipart/form-data)
        ├── 201 OK → data/archive/
        └── Fehler → data/upload_error/  (3 Retries: 30s/60s/120s)
```

## Dateinamen-Konvention (AWARE-kompatibel)

- UBX-Binärdaten: `{STATION_ID}_YYYYMMDD_HHMM.ubx`  → Server: `data/staging/` → Darkside SFTP
- Device-Log:     `{STATION_ID}_log_YYYYMMDD_HHMM.txt` → Server: Dashboard-Karte + Alerts

Device-Log-Format (GPS-Koordinaten-Zeile triggert AWARE-Kartendarstellung):
```
2026-05-01 12:01:00 [INFO ] Position update: lat=47.4083744, lon=8.5057600, height=569 m
```
Regex des Servers: `Position update:\s*lat=([-\d.]+),\s*lon=([-\d.]+)`

## Tunnel-Ziel

- Host: `192.33.89.14` (LuckyLuke)
- SSH-Key: `/home/pi/.ssh/luckyluke`
- Port-Schema: T010 = 2010, T011 = 2011, ...

## Diagnose-Befehle

```bash
# Modem erkannt?
lsusb | grep -i quectel

# LTE-Verbindungsstatus
sudo qmicli -d /dev/cdc-wdm0 --wds-get-packet-service-status
ip addr show wwan0

# Modem-Boot-Log
cat /home/pi/aware-pi-logger/logs/modem.log

# u-blox Chip-Konfiguration (läuft einmalig @reboot)
cat /home/pi/aware-pi-logger/logs/gnss_config.log

# RAWX-Logger (live)
sudo systemctl status gnss-logger
sudo journalctl -u gnss-logger -f
tail -f /home/pi/aware-pi-logger/logs/rawx_logger.log

# Daten-Verzeichnisse prüfen
ls -lh /home/pi/aware-pi-logger/data/rawx/
ls -lh /home/pi/aware-pi-logger/data/upload_ready/

# Upload-Log
tail -f /home/pi/aware-pi-logger/logs/uploader.log

# Tunnel-Status
sudo systemctl status autossh
```

## Installierte Pakete

- `libqmi-utils` – `qmicli`
- `udhcpc` – DHCP-Client für `wwan0`
- `autossh` – stabiler SSH-Tunnel
- `python3-serial` / `pyserial` – GNSS-Serial-Kommunikation
- `pyubx2` – UBX-Protokoll-Parser (UBXReader, UBXMessage)
- `requests` – HTTP-Upload zu AWARE
