#!/bin/bash
# aware-pi-logger install script
# Run once on a fresh Raspberry Pi (Debian Bookworm, arm64).
# Usage: sudo bash install.sh

set -e

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
CONFIG="$REPO_DIR/config/config.env"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()    { echo -e "${GREEN}[install]${NC} $*"; }
warn()    { echo -e "${YELLOW}[warn]${NC} $*"; }
error()   { echo -e "${RED}[error]${NC} $*"; exit 1; }

[ "$EUID" -ne 0 ] && error "Run with sudo: sudo bash install.sh"

# ── 1. Config ─────────────────────────────────────────────────────────────────
if [ ! -f "$CONFIG" ]; then
    warn "config/config.env not found – copying from example."
    cp "$REPO_DIR/config/config.env.example" "$CONFIG"
    warn "Edit $CONFIG before continuing (TUNNEL_PORT, SSH_KEY, etc.)."
    warn "Then re-run this script."
    exit 0
fi
source "$CONFIG"

# ── 2. Packages ───────────────────────────────────────────────────────────────
info "Installing packages..."
apt-get update -qq
apt-get install -y libqmi-utils udhcpc autossh python3-serial python3-venv

# ── 3. Python virtual environment ────────────────────────────────────────────
VENV="$REPO_DIR/venv"
if [ ! -d "$VENV" ]; then
    info "Creating Python venv at $VENV..."
    python3 -m venv "$VENV"
fi
info "Installing Python packages into venv..."
"$VENV/bin/pip" install --quiet pyubx2 requests pyserial

# ── 4. Disable ModemManager (conflicts with qmicli) ───────────────────────────
info "Disabling ModemManager..."
systemctl stop ModemManager 2>/dev/null || true
systemctl disable ModemManager 2>/dev/null || true

# ── 5. Data directories ───────────────────────────────────────────────────────
info "Creating data directories..."
mkdir -p "$REPO_DIR/data/rawx" "$REPO_DIR/data/upload_ready" \
         "$REPO_DIR/data/archive" "$REPO_DIR/data/upload_error"
chown -R pi:pi "$REPO_DIR/data"

# ── 6. Root crontab: modem + u-blox config + uploader ────────────────────────
info "Registering crontab entries..."
chmod +x "$REPO_DIR/modem/start-qmi.sh"
PYTHON="$REPO_DIR/venv/bin/python"
CRON_MODEM="@reboot $REPO_DIR/modem/start-qmi.sh >> $REPO_DIR/logs/modem.log 2>&1"
CRON_UPLOAD="5 * * * * $PYTHON $REPO_DIR/gnss/uploader.py >> $REPO_DIR/logs/uploader.log 2>&1"
CRON_HK="0 3 * * * $PYTHON $REPO_DIR/gnss/housekeeping.py >> $REPO_DIR/logs/housekeeping.log 2>&1"
(
  crontab -l 2>/dev/null \
    | grep -v "start-qmi.sh\|uploader.py\|housekeeping.py"
  echo "$CRON_MODEM"
  echo "$CRON_UPLOAD"
  echo "$CRON_HK"
) | crontab -

# ── 7. AutoSSH systemd service ────────────────────────────────────────────────
info "Installing autossh.service (tunnel port ${TUNNEL_PORT})..."
sed \
    -e "s|__SSH_KEY__|${SSH_KEY}|g" \
    -e "s|__TUNNEL_PORT__|${TUNNEL_PORT}|g" \
    -e "s|__TUNNEL_USER__|${TUNNEL_USER}|g" \
    -e "s|__TUNNEL_HOST__|${TUNNEL_HOST}|g" \
    "$REPO_DIR/tunnel/autossh.service.template" \
    > /etc/systemd/system/autossh.service

systemctl daemon-reload
systemctl enable autossh
systemctl restart autossh

# ── 8. GNSS RAWX logger systemd service ──────────────────────────────────────
info "Installing gnss-logger.service (rawx_logger)..."
cat > /etc/systemd/system/gnss-logger.service << EOF
[Unit]
Description=aware-pi GNSS RAWX Logger (u-blox -> UBX binary)
After=network.target

[Service]
User=pi
WorkingDirectory=$REPO_DIR
ExecStartPre=/bin/sleep 60
ExecStartPre=$REPO_DIR/venv/bin/python $REPO_DIR/gnss/config_ublox.py
ExecStart=$REPO_DIR/venv/bin/python $REPO_DIR/gnss/rawx_logger.py
Restart=always
RestartSec=30

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable gnss-logger
systemctl restart gnss-logger

# ── 9. Done ───────────────────────────────────────────────────────────────────
info "Installation complete."
echo ""
echo "  Modem log    : $REPO_DIR/logs/modem.log  (after reboot)"
echo "  GNSS config  : $REPO_DIR/logs/gnss_config.log  (after reboot)"
echo "  RAWX logger  : $REPO_DIR/logs/rawx_logger.log"
echo "  Uploader     : $REPO_DIR/logs/uploader.log"
echo "  Data dirs    : $REPO_DIR/data/"
echo "  Tunnel port  : ${TUNNEL_PORT} on ${TUNNEL_HOST}"
echo ""
echo "  Check status:"
echo "    sudo systemctl status autossh"
echo "    sudo systemctl status gnss-logger"
echo "    sudo journalctl -u gnss-logger -f"
