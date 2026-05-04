#!/bin/bash
# LTE connectivity watchdog — invoked periodically via cron.
# Checks if wwan0 is up and reachable; recovers if not.

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DEVICE=/dev/cdc-wdm0
IFACE=wwan0
PING_HOST=8.8.8.8

has_ip()   { ip addr show "$IFACE" 2>/dev/null | grep -q 'inet '; }
can_ping() { ping -c 2 -W 5 -I "$IFACE" "$PING_HOST" >/dev/null 2>&1; }
qmi_connected() {
    [ -e "$DEVICE" ] && \
    qmicli -d "$DEVICE" --wds-get-packet-service-status 2>/dev/null | grep -q "'connected'"
}

if has_ip && can_ping; then
    exit 0
fi

echo "[$(date)] LTE connectivity lost — starting recovery..."

# Kill any hung udhcpc instance on this interface
pkill -f "udhcpc.*-i $IFACE" 2>/dev/null || true
sleep 1

if qmi_connected; then
    # QMI data session is alive — only DHCP is broken
    echo "[$(date)] QMI session active, re-running DHCP only..."
    if /usr/sbin/udhcpc -q -f -t 10 -T 5 -i "$IFACE"; then
        echo -e "nameserver 8.8.8.8\nnameserver 1.1.1.1" > /etc/resolv.conf
        echo "[$(date)] DHCP recovery successful."
    else
        echo "[$(date)] DHCP recovery failed."
        exit 1
    fi
else
    # Full reconnect needed
    echo "[$(date)] QMI session not active, running full start-qmi.sh..."
    "$SCRIPT_DIR/modem/start-qmi.sh"
fi

echo "[$(date)] Recovery result:"
ip addr show "$IFACE"
