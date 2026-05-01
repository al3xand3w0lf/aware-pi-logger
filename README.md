# aware-pi-logger

IoT GNSS data logger for Raspberry Pi (Debian Bookworm, arm64).

## Hardware

| Component | Details |
|---|---|
| SBC | Raspberry Pi |
| GNSS | u-blox (USB or GPIO UART) |
| LTE Modem | Quectel EC25/EG-25 (QMI interface) |
| Tunnel | AutoSSH reverse tunnel → LuckyLuke |

## Quick start on a new Pi

```bash
# 1. Clone
git clone <repo-url> /home/pi/aware-pi-logger
cd /home/pi/aware-pi-logger

# 2. First run: copies config.env.example → config/config.env, then exits
sudo bash install.sh

# 3. Edit config (set TUNNEL_PORT, SSH_KEY, GNSS_DEVICE, APN, ...)
nano config/config.env

# 4. Copy SSH key for tunnel
scp user@luckyluke:~/.ssh/luckyluke ~/.ssh/luckyluke
chmod 600 ~/.ssh/luckyluke

# 5. Accept host key (once, interactive)
ssh -i ~/.ssh/luckyluke pi@<TUNNEL_HOST> "echo ok"

# 6. Full install
sudo bash install.sh
```

## Directory layout

```
aware-pi-logger/
├── install.sh              ← full setup for a fresh Pi
├── config/
│   ├── config.env.example  ← template (committed)
│   └── config.env          ← your secrets (git-ignored)
├── modem/
│   ├── start-qmi.sh        ← LTE connection via QMI
│   └── SETUP.md
├── tunnel/
│   ├── autossh.service.template
│   └── SETUP.md
├── gnss/
│   └── logger.py           ← u-blox NMEA logger → CSV
└── logs/                   ← git-ignored
```

## Services after install

| Service | Description |
|---|---|
| `gnss-logger.service` | GNSS data logger, starts at boot |
| `autossh.service` | Reverse SSH tunnel to LuckyLuke |
| root crontab `@reboot` | LTE modem QMI connection |

## Multiple devices

Each Pi needs its own `TUNNEL_PORT` in `config/config.env`:

| Device | Port |
|---|---|
| Ikarus-1 | 2010 |
| Ikarus-2 | 2011 |
| Ikarus-3 | 2012 |

## Logs

```bash
# GNSS
sudo journalctl -u gnss-logger -f

# Tunnel
sudo journalctl -u autossh -f

# Modem (after reboot)
cat logs/modem.log
```
