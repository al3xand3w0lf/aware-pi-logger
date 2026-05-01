# aware-pi-logger – Kontext für Claude

## Projektübersicht

IoT GNSS-Datenlogger auf Raspberry Pi (arm64, Debian Bookworm).  
Gerätename: **Ikarus**. Jedes Gerät ist eine eigene Instanz dieses Repos.

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

## Services & Autostart

| Mechanismus | Datei | Zweck |
|---|---|---|
| root `@reboot` crontab | `modem/start-qmi.sh` | LTE-Verbindung via QMI |
| systemd `autossh.service` | `tunnel/autossh.service.template` | Reverse-SSH-Tunnel → LuckyLuke |
| systemd `gnss-logger.service` | `gnss/logger.py` | GNSS-Daten loggen |

## Konfiguration

Alle gerätespezifischen Werte stehen in `config/config.env` (nicht im Repo).  
Vorlage: `config/config.env.example`.  
Wichtigste Variable: `TUNNEL_PORT` (pro Gerät eindeutig, z. B. 2010, 2011, ...).

## Tunnel-Ziel

- Host: `192.33.89.14` (LuckyLuke)
- SSH-Key: `/home/pi/.ssh/luckyluke`
- Port-Schema: Ikarus-1 = 2010, Ikarus-2 = 2011, ...

## GNSS-Logger

- Quelle: u-blox NMEA über Serial (USB oder GPIO-UART)
- Gerät und Baudrate in `config/config.env` (`GNSS_DEVICE`, `GNSS_BAUD`)
- Ausgabe: CSV-Dateien in `logs/`
- Implementierung: `gnss/logger.py` (parst GGA-Sätze)

## Diagnose-Befehle

```bash
# Modem erkannt?
lsusb | grep -i quectel

# LTE-Verbindungsstatus
sudo qmicli -d /dev/cdc-wdm0 --wds-get-packet-service-status
ip addr show wwan0

# Modem-Boot-Log
cat /home/pi/aware-pi-logger/logs/modem.log

# Tunnel-Status
sudo systemctl status autossh

# GNSS-Logger
sudo systemctl status gnss-logger
sudo journalctl -u gnss-logger -f
```

## Installierte Pakete

- `libqmi-utils` – `qmicli`
- `udhcpc` – DHCP-Client für `wwan0`
- `autossh` – stabiler SSH-Tunnel
- `python3-serial` – GNSS-Serial-Kommunikation
