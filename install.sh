#!/usr/bin/env bash
set -e
RED='\033[1;31m'; NC='\033[0m'
[ "$(id -u)" -eq 0 ] || { echo "Run as root: sudo ./install.sh"; exit 1; }
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

echo -e "${RED}=== VPS Bot installer ===${NC}"
echo "1) Ubuntu   2) Debian"
read -rp "Your OS [1/2]: " OSC

apt update -y
apt install -y python3 python3-venv python3-pip snapd curl
systemctl enable --now snapd.socket 2>/dev/null || true
if ! command -v lxc >/dev/null 2>&1; then
  snap install lxd || { sleep 5; snap install lxd; }
  export PATH="$PATH:/snap/bin"
fi
export PATH="$PATH:/snap/bin"
lxd init --auto || true

python3 -m venv venv
./venv/bin/pip install -q -r requirements.txt

read -rp "Discord Bot Token: " TOKEN
read -rp "Main Admin Discord ID: " ADMIN
cat > .env <<ENV
DISCORD_TOKEN=$TOKEN
MAIN_ADMIN_ID=$ADMIN
PREFIX=!
BOT_NAME=VPS Bot
FOOTER=Made by Crimson
VPS_IMAGE=ubuntu:22.04
MAX_VPS_PER_USER=3
PORT_QUOTA=5
ALERT_THRESHOLD=90
ENV
chmod 600 .env

cat > /etc/systemd/system/bot.service <<SVC
[Unit]
Description=VPS Discord Bot
After=network-online.target snap.lxd.daemon.service
Wants=network-online.target

[Service]
WorkingDirectory=$DIR
Environment=PATH=/snap/bin:/usr/local/bin:/usr/bin:/bin
ExecStart=$DIR/venv/bin/python $DIR/bot.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
SVC
systemctl daemon-reload
systemctl enable --now bot

echo -e "${RED}Installed. Bot is running.${NC}"
echo "  systemctl status bot | journalctl -u bot -f | systemctl restart bot"
