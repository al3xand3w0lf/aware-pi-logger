# How to Setup AutoSSH Reverse Tunnel (Ikarus → LuckyLuke)

## Ziel

Beim Hochfahren des Raspberry Pi (Ikarus) wird automatisch ein Reverse-SSH-Tunnel zu LuckyLuke aufgebaut. LuckyLuke kann dann über den Tunnel per `ssh pi@localhost -p 2010` auf Ikarus zugreifen — auch wenn Ikarus hinter NAT oder einer Firewall sitzt.

---

## Voraussetzungen

- Raspberry Pi (Ikarus) mit Raspberry Pi OS (Debian Bookworm)
- LuckyLuke erreichbar unter `192.33.89.14`
- SSH-Keypair für die Verbindung zu LuckyLuke liegt bereit (z. B. auf einem anderen Gerät oder auf LuckyLuke selbst)

---

## Schritt 1: SSH-Key auf Ikarus kopieren

Den privaten Key (`luckyluke`) und den öffentlichen Key (`luckyluke.pub`) in das `.ssh`-Verzeichnis des `pi`-Users kopieren:

```bash
# Beispiel: Key von LuckyLuke auf Ikarus kopieren (von LuckyLuke aus ausführen)
scp ~/.ssh/luckyluke pi@<IKARUS-IP>:~/.ssh/luckyluke
scp ~/.ssh/luckyluke.pub pi@<IKARUS-IP>:~/.ssh/luckyluke.pub
```

Nach dem Kopieren die Berechtigungen des privaten Keys auf Ikarus setzen — SSH verweigert Keys mit zu offenen Rechten:

```bash
chmod 600 ~/.ssh/luckyluke
```

Ergebnis prüfen:

```bash
ls -la ~/.ssh/
# -rw------- 1 pi pi 411 ... luckyluke
# -rw-r--r-- 1 pi pi 101 ... luckyluke.pub
```

---

## Schritt 2: AutoSSH installieren

```bash
sudo apt update
sudo apt install -y autossh
```

Installation prüfen:

```bash
which autossh
# /usr/bin/autossh
```

---

## Schritt 3: SSH-Verbindung zu LuckyLuke testen

Vor dem Einrichten des Services sicherstellen, dass die Verbindung mit dem Key funktioniert. Der Host-Key wird dabei automatisch in `~/.ssh/known_hosts` gespeichert — das ist wichtig, damit der spätere Service (im `BatchMode`) nicht hängt:

```bash
ssh -i ~/.ssh/luckyluke -o "BatchMode=yes" -o "ConnectTimeout=10" -o "StrictHostKeyChecking=no" pi@192.33.89.14 "echo 'SSH connection successful'"
# Ausgabe: SSH connection successful
```

---

## Schritt 4: Systemd Service-Datei erstellen

```bash
sudo nano /etc/systemd/system/autossh.service
```

Folgenden Inhalt einfügen (Port `2010` ist der Tunnel-Port für diesen Ikarus auf LuckyLuke):

```ini
[Unit]
Description=AutoSSH Reverse Tunnel
After=network.target

[Service]
User=pi
ExecStart=/usr/bin/autossh -M 0 -N \
  -i /home/pi/.ssh/luckyluke \
  -o "ServerAliveInterval=30" \
  -o "ServerAliveCountMax=3" \
  -o "TCPKeepAlive=yes" \
  -o "ExitOnForwardFailure=yes" \
  -o "ConnectTimeout=10" \
  -o "BatchMode=yes" \
  -R 2010:localhost:22 pi@192.33.89.14
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

**Erklärung der wichtigsten Parameter:**

| Parameter | Bedeutung |
|---|---|
| `-M 0` | Kein Monitoring-Port (autossh überwacht via ServerAlive) |
| `-N` | Keine Remote-Befehle ausführen, nur Tunnel |
| `-i /home/pi/.ssh/luckyluke` | Privater Key für die Verbindung |
| `ServerAliveInterval=30` | Alle 30s Keep-Alive-Paket senden |
| `ServerAliveCountMax=3` | Nach 3 ausbleibenden Antworten Verbindung trennen |
| `ExitOnForwardFailure=yes` | Beendet SSH wenn Port-Forwarding fehlschlägt (damit autossh neu starten kann) |
| `BatchMode=yes` | Kein interaktiver Passwort-Prompt |
| `-R 2010:localhost:22` | Port 2010 auf LuckyLuke → Port 22 auf Ikarus |
| `Restart=always` | Systemd startet den Service bei Absturz neu |
| `RestartSec=10` | 10s warten vor Neustart |

---

## Schritt 5: Service aktivieren und starten

```bash
sudo systemctl daemon-reload
sudo systemctl enable autossh
sudo systemctl start autossh
```

---

## Schritt 6: Status prüfen

```bash
sudo systemctl status autossh
```

Erwartete Ausgabe (gekürzt):

```
● autossh.service - AutoSSH Reverse Tunnel
     Active: active (running) since ...
   Main PID: XXXX (autossh)
             ├─XXXX /usr/lib/autossh/autossh -M 0 -N ...
             └─XXXX /usr/bin/ssh -N -i /home/pi/.ssh/luckyluke ... -R 2010:localhost:22 pi@192.33.89.14
```

---

## Schritt 7: Verbindung von LuckyLuke aus testen

Auf LuckyLuke einloggen und Tunnel testen:

```bash
ssh pi@localhost -p 2010
```

Offene Tunnel-Ports auf LuckyLuke anzeigen:

```bash
sudo netstat -tuln | grep 2010
```

---

## Troubleshooting

**Service startet nicht:**
```bash
journalctl -u autossh -n 50
```

**SSH-Verbindung schlägt fehl:**
```bash
# Verbindung manuell mit verbose testen
ssh -v -i ~/.ssh/luckyluke pi@192.33.89.14
```

**known_hosts fehlt (BatchMode schlägt fehl):**
```bash
# Host-Key manuell akzeptieren (einmalig ohne BatchMode)
ssh -i ~/.ssh/luckyluke pi@192.33.89.14
```

**SSH-Dienst auf Ikarus prüfen:**
```bash
sudo systemctl status ssh
```

**Logs auf Ikarus:**
```bash
sudo tail -f /var/log/auth.log
```

---

## Mehrere Ikarus-Geräte

Jedes Ikarus-Gerät bekommt einen eigenen Port auf LuckyLuke:

| Gerät | Port |
|---|---|
| Ikarus-1 | 2010 |
| Ikarus-2 | 2011 |
| Ikarus-3 | 2012 |

Den Port `-R 2010:localhost:22` in der Service-Datei entsprechend anpassen.
