# Quectel EG-25 / EC25 LTE Modem – Setup via QMI Interface

Getestet auf: Raspberry Pi (arm64, Debian Bookworm), Quectel EC25/EG-25, Swisscom SIM

---

## Voraussetzungen

- Modem via USB verbunden
- SIM-Karte eingelegt
- Root-Zugriff (`sudo`)

---

## 1. Pakete installieren

```bash
sudo apt update && sudo apt install libqmi-utils udhcpc
```

---

## 2. Gerät prüfen

USB-Erkennung:
```bash
lsusb | grep -i quectel
# Erwartet: Bus 00x Device 00x: ID 2c7c:0125 Quectel Wireless Solutions Co., Ltd. EC25 LTE modem
```

QMI-Device und Netzwerk-Interface:
```bash
ls /dev/cdc-wdm0    # QMI control device
ls /sys/class/net/  # wwan0 muss vorhanden sein
```

---

## 3. ModemManager deaktivieren

**Wichtig:** ModemManager belegt `/dev/cdc-wdm0` und blockiert `qmicli`.  
Er muss vor dem Einsatz von libqmi dauerhaft deaktiviert werden.

```bash
sudo systemctl stop ModemManager
sudo systemctl disable ModemManager
```

Prüfen ob das Device jetzt frei ist:
```bash
sudo fuser /dev/cdc-wdm0
# Keine Ausgabe = frei
```

---

## 4. Verbindung manuell aufbauen

```bash
# 1. Betriebsmodus prüfen
sudo qmicli -d /dev/cdc-wdm0 --dms-get-operating-mode

# 2. Online schalten (falls nicht bereits online)
sudo qmicli -d /dev/cdc-wdm0 --dms-set-operating-mode='online'

# 3. Interface runterfahren, Raw-IP aktivieren, wieder hochfahren
sudo ip link set wwan0 down
echo 'Y' | sudo tee /sys/class/net/wwan0/qmi/raw_ip
sudo ip link set wwan0 up

# 4. Netzwerkverbindung starten (Swisscom APN)
sudo qmicli -p -d /dev/cdc-wdm0 \
  --device-open-net='net-raw-ip|net-no-qos-header' \
  --wds-start-network="apn='gprs.swisscom.ch',username='gprs',password='gprs',ip-type=4" \
  --client-no-release-cid

# 5. IP-Adresse per DHCP holen
sudo udhcpc -q -f -i wwan0
```

---

## 5. Verbindung prüfen

```bash
ifconfig wwan0
# Erwartet: inet 10.x.x.x ...

ping -I wwan0 -c 5 sixfab.com
```

---

## 6. Autostart beim Boot

Das Script `/home/pi/workspace_modem/start-qmi.sh` übernimmt den kompletten Ablauf.  
Es ist in der root-Crontab als `@reboot`-Job eingetragen:

```bash
sudo crontab -l
# @reboot /home/pi/workspace_modem/start-qmi.sh >> /home/pi/workspace_modem/modem_start.log 2>&1
```

Log nach dem Boot prüfen:
```bash
cat /home/pi/workspace_modem/modem_start.log
```

---

## Fehlerbehebung

### `udhcpc` nicht gefunden
```
udhcpc: command not found
```
**Ursache:** Paket nicht installiert.  
**Lösung:**
```bash
sudo apt install udhcpc
```

---

### `endpoint hangup` / `Resource temporarily unavailable`
```
error: couldn't create client for the 'wda' service: CID allocation failed in the CTL client: endpoint hangup
```
**Ursache:** ModemManager hält `/dev/cdc-wdm0` belegt.  
**Lösung:**
```bash
sudo systemctl stop ModemManager
sudo systemctl disable ModemManager
```
Danach `qmicli`-Befehl wiederholen.

---

### WDA Internal Error
```
error: couldn't create client for the 'wda' service: QMI protocol error (3): 'Internal'
```
**Ursache:** Der EC25/EG-25 unterstützt den WDA-Service (Data Format) nicht vollständig.  
**Lösung:** Schritt `--wda-get-data-format` überspringen. `raw_ip` manuell auf `Y` setzen (siehe Schritt 4) – das ist ausreichend.

---

### Kein `/dev/cdc-wdm0`
**Ursache:** Modem noch nicht bereit, falscher USB-Mode, oder fehlender Kernel-Treiber.  
**Diagnose:**
```bash
lsusb | grep -i quectel   # Modem erkannt?
dmesg | grep -i qmi       # Kernel-Treiber geladen?
dmesg | grep -i wwan
```
Beim Boot kann es 10–20 Sekunden dauern bis das Device erscheint. Das Startup-Script wartet automatisch bis zu 60 Sekunden.

---

### `wwan0` nicht vorhanden
**Ursache:** Kernel-Modul `qmi_wwan` nicht geladen.  
**Lösung:**
```bash
sudo modprobe qmi_wwan
```
Für dauerhaftes Laden:
```bash
echo 'qmi_wwan' | sudo tee /etc/modules-load.d/qmi_wwan.conf
```

---

### DHCP schlägt fehl / keine IP
**Ursache:** WDS-Netzwerkverbindung noch nicht aufgebaut, falscher APN, oder `raw_ip` nicht gesetzt.  
**Diagnose:**
```bash
cat /sys/class/net/wwan0/qmi/raw_ip   # Muss 'Y' sein
sudo qmicli -d /dev/cdc-wdm0 --wds-get-packet-service-status
```

---

### APN für andere Schweizer Anbieter

| Anbieter  | APN                  | User      | Passwort  |
|-----------|----------------------|-----------|-----------|
| Swisscom  | `gprs.swisscom.ch`   | `gprs`    | `gprs`    |
| Sunrise   | `internet`           | (leer)    | (leer)    |
| Salt      | `internet.salt.ch`   | (leer)    | (leer)    |

---

## Dateiübersicht

| Datei                                      | Beschreibung                        |
|--------------------------------------------|-------------------------------------|
| `/home/pi/workspace_modem/start-qmi.sh`    | Startup-Script                      |
| `/home/pi/workspace_modem/modem_start.log` | Boot-Log des Startup-Scripts        |
| `/home/pi/workspace_modem/SETUP.md`        | Diese Dokumentation                 |
