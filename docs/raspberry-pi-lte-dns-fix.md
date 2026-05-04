# Raspberry Pi LTE DNS Fix

## Problem

Der Raspberry Pi ist via LTE-Modem (Quectel, `qmi_wwan` Treiber) mit dem Internet verbunden. Die Netzwerkschnittstelle `wwan0` wird von `udhcpc` verwaltet. DNS-Auflösung schlägt fehl (`Temporary failure in name resolution`), obwohl eine IP-Adresse zugewiesen ist und bestehende TCP-Verbindungen (z. B. Reverse-SSH-Tunnel) funktionieren.

### Ursache

- `udhcpc` bekommt vom Carrier DNS-Server (`193.5.23.8`, `193.247.204.8`), schreibt diese aber nicht zuverlässig in `/etc/resolv.conf`
- NetworkManager ist aktiv und überschreibt `/etc/resolv.conf` bei Ereignissen
- `wwan0` wird nicht von NetworkManager verwaltet (kein NM-Verbindungsprofil)

### Diagnose

```bash
# Interface-Status
ifconfig

# DNS-Test (schlägt fehl)
ping -c 3 google.com

# IP direkt erreichbar (kein DNS nötig)
ping -c 3 8.8.8.8

# Was verwaltet wwan0?
journalctl -b | grep wwan0
# → zeigt udhcpc mit Carrier-DNS in DHCP-Antwort

# NetworkManager verwaltet wwan0 nicht
nmcli con show
# → kein Eintrag für wwan0
```

## Lösung

### 1. resolv.conf mit zuverlässigem DNS befüllen und sperren

```bash
echo -e "nameserver 8.8.8.8\nnameserver 8.8.4.4" | sudo tee /etc/resolv.conf
sudo chattr +i /etc/resolv.conf
```

`chattr +i` verhindert dass root oder irgendein Dienst die Datei überschreibt.

### 2. NetworkManager anweisen, DNS nicht zu verwalten

```bash
sudo mkdir -p /etc/NetworkManager/conf.d
echo -e "[main]\ndns=none" | sudo tee /etc/NetworkManager/conf.d/no-dns.conf
sudo nmcli general reload
```

### 3. Cron-Job als Sicherheitsnetz (alle 5 Minuten)

```bash
sudo nano /etc/cron.d/fix-dns
```

Inhalt (eine Zeile):

```
*/5 * * * * root chattr -i /etc/resolv.conf 2>/dev/null; echo nameserver 8.8.8.8 > /etc/resolv.conf; echo nameserver 8.8.4.4 >> /etc/resolv.conf; chattr +i /etc/resolv.conf
```

Der Cron-Job entsperrt kurz, schreibt DNS neu, sperrt wieder — übersteht udhcpc-Reconnects und Reboots.

### Verifikation

```bash
ping -c 3 google.com
cat /etc/resolv.conf
cat /etc/NetworkManager/conf.d/no-dns.conf
cat /etc/cron.d/fix-dns
```

## Resultat

| Komponente | Status |
|---|---|
| `/etc/resolv.conf` | gesperrt (`chattr +i`), `8.8.8.8` + `8.8.4.4` |
| NetworkManager | `dns=none`, greift resolv.conf nicht an |
| Cron `/etc/cron.d/fix-dns` | stellt DNS alle 5 Min sicher |

DNS übersteht jetzt: udhcpc-Reconnects, NetworkManager-Neustart, System-Reboot.
