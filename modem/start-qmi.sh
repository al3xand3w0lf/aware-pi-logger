#!/bin/bash
# Reads APN/credentials from config.env if present, falls back to defaults.

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
CONFIG="$SCRIPT_DIR/config/config.env"

DEVICE=/dev/cdc-wdm0
IFACE=wwan0
APN=gprs.swisscom.ch
MODEM_USER=gprs
MODEM_PASS=gprs

[ -f "$CONFIG" ] && source "$CONFIG"

echo "[$(date)] Starting QMI modem connection..."

for i in $(seq 1 30); do
    [ -e "$DEVICE" ] && break
    echo "[$(date)] Waiting for $DEVICE... ($i/30)"
    sleep 2
done

if [ ! -e "$DEVICE" ]; then
    echo "[$(date)] ERROR: $DEVICE not found after 60s, aborting."
    exit 1
fi

qmicli -d "$DEVICE" --dms-set-operating-mode='online'

ip link set "$IFACE" down
echo 'Y' | tee /sys/class/net/$IFACE/qmi/raw_ip
ip link set "$IFACE" up

qmicli -p -d "$DEVICE" \
    --device-open-net='net-raw-ip|net-no-qos-header' \
    --wds-start-network="apn='${APN}',username='${MODEM_USER}',password='${MODEM_PASS}',ip-type=4" \
    --client-no-release-cid

udhcpc -q -f -i "$IFACE"

echo "[$(date)] Done. Interface state:"
ip addr show "$IFACE"
