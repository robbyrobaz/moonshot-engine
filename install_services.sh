#!/bin/bash
# Install Moonshot v2 systemd user services
set -e

SYSTEMD_DIR="$HOME/.config/systemd/user"
SERVICE_DIR="$(cd "$(dirname "$0")" && pwd)/systemd"

mkdir -p "$SYSTEMD_DIR"

echo "Installing systemd user services..."
for f in "$SERVICE_DIR"/*.service "$SERVICE_DIR"/*.timer; do
    cp "$f" "$SYSTEMD_DIR/"
    echo "  Installed $(basename "$f")"
done

systemctl --user daemon-reload

echo "Enabling timers..."
systemctl --user enable blofin-moonshot-v2.timer
systemctl --user enable blofin-moonshot-v2-social.timer
systemctl --user enable blofin-moonshot-v2-dashboard.service

echo "Starting services..."
systemctl --user start blofin-moonshot-v2.timer
systemctl --user start blofin-moonshot-v2-social.timer
systemctl --user start blofin-moonshot-v2-dashboard.service

echo ""
echo "Done. Check status with:"
echo "  systemctl --user status blofin-moonshot-v2.timer"
echo "  systemctl --user status blofin-moonshot-v2-social.timer"
echo "  systemctl --user status blofin-moonshot-v2-dashboard.service"
echo ""
echo "Manual run: systemctl --user start blofin-moonshot-v2.service"
echo "Dashboard: http://localhost:8893"
