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
apt-get install -y libqmi-utils udhcpc autossh python3-serial

# ── 3. Disable ModemManager (conflicts with qmicli) ───────────────────────────
info "Disabling ModemManager..."
systemctl stop ModemManager 2>/dev/null || true
systemctl disable ModemManager 2>/dev/null || true

# ── 4. Modem startup (root crontab) ───────────────────────────────────────────
info "Registering modem startup in root crontab..."
chmod +x "$REPO_DIR/modem/start-qmi.sh"
CRON_LINE="@reboot $REPO_DIR/modem/start-qmi.sh >> $REPO_DIR/logs/modem.log 2>&1"
( crontab -l 2>/dev/null | grep -v "start-qmi.sh"; echo "$CRON_LINE" ) | crontab -

# ── 5. AutoSSH systemd service ────────────────────────────────────────────────
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

# ── 6. GNSS logger systemd service ───────────────────────────────────────────
info "Installing gnss-logger.service..."
cat > /etc/systemd/system/gnss-logger.service << EOF
[Unit]
Description=aware-pi GNSS Logger (u-blox)
After=network.target

[Service]
User=pi
WorkingDirectory=$REPO_DIR
ExecStart=/usr/bin/python3 $REPO_DIR/gnss/logger.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable gnss-logger
systemctl restart gnss-logger

# ── 7. Done ───────────────────────────────────────────────────────────────────
info "Installation complete."
echo ""
echo "  Modem log  : $REPO_DIR/logs/modem.log  (after reboot)"
echo "  GNSS log   : $REPO_DIR/logs/"
echo "  Tunnel port: ${TUNNEL_PORT} on ${TUNNEL_HOST}"
echo ""
echo "  Check status:"
echo "    sudo systemctl status autossh"
echo "    sudo systemctl status gnss-logger"
