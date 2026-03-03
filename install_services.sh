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
systemctl --user enable moonshot-engine.timer
systemctl --user enable moonshot-engine-social.timer
systemctl --user enable moonshot-engine-dashboard.service

echo "Starting services..."
systemctl --user start moonshot-engine.timer
systemctl --user start moonshot-engine-social.timer
systemctl --user start moonshot-engine-dashboard.service

echo ""
echo "Done. Check status with:"
echo "  systemctl --user status moonshot-engine.timer"
echo "  systemctl --user status moonshot-engine-social.timer"
echo "  systemctl --user status moonshot-engine-dashboard.service"
echo ""
echo "Manual run: systemctl --user start moonshot-engine.service"
echo "Dashboard: http://localhost:8893"
