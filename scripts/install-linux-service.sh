#!/usr/bin/env bash
# Installs a systemd service (Raspberry Pi OS or any Linux with systemd) so
# the bot starts on boot, restarts if it crashes, and updates itself when new
# code reaches the main branch on GitHub.
#
# Run from the project folder:  ./scripts/install-linux-service.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="$ROOT/.venv/bin/python"
SERVICE=/etc/systemd/system/kqbot.service

[ -x "$PYTHON" ] || { echo "Couldn't find $PYTHON. Create the virtual environment first (see README)."; exit 1; }
[ -f "$ROOT/.env" ] || { echo "Couldn't find $ROOT/.env. Copy .env.example to .env and add your token."; exit 1; }

sudo tee "$SERVICE" > /dev/null <<UNIT
[Unit]
Description=Fiesta KQ Bot (kept running and up to date by its supervisor)
After=network-online.target
Wants=network-online.target

[Service]
User=$(id -un)
WorkingDirectory=$ROOT
ExecStart=$PYTHON -m kqbot.supervise
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
UNIT

sudo systemctl daemon-reload
sudo systemctl enable --now kqbot
echo "Installed and started. Check it with: systemctl status kqbot"
echo "Logs: $ROOT/logs  (kqbot.log = the bot, supervisor.log = restarts and updates)"
