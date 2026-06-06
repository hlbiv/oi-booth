#!/bin/bash
# oi-booth installer — run once on the Pi as the pi user
set -e

INSTALL_DIR="$HOME/oi-booth"
VENV="$INSTALL_DIR/venv"

echo "==> Updating system packages"
sudo apt-get update -qq
sudo apt-get install -y \
  python3 python3-venv python3-pip \
  libsdl2-dev python3-opencv \
  cups libcups2-dev \
  fonts-dejavu-core

echo "==> Creating virtualenv"
python3 -m venv "$VENV"
"$VENV/bin/pip" install --upgrade pip -q

echo "==> Installing Python dependencies"
"$VENV/bin/pip" install -r "$INSTALL_DIR/requirements.txt" -q

echo "==> Copying pibooth plugin"
PLUGIN_DIR="$HOME/.config/pibooth/plugins"
mkdir -p "$PLUGIN_DIR"
cp "$INSTALL_DIR/booth/plugin.py" "$PLUGIN_DIR/oi_booth_plugin.py"

echo "==> Copying default config (if none exists)"
CFG="$HOME/.config/pibooth/pibooth.cfg"
if [ ! -f "$CFG" ]; then
  mkdir -p "$(dirname "$CFG")"
  cp "$INSTALL_DIR/config/pibooth.cfg" "$CFG"
  echo "    Wrote $CFG"
else
  echo "    Config already exists — skipping (diff $INSTALL_DIR/config/pibooth.cfg $CFG to review changes)"
fi

echo "==> Installing USB auto-mount udev rule"
sudo cp "$INSTALL_DIR/scripts/usb-mount.rules" /etc/udev/rules.d/99-oi-booth-usb.rules
sudo udevadm control --reload-rules

echo "==> Registering systemd services"
sudo cp "$INSTALL_DIR/services/oi-booth.service" /etc/systemd/system/
sudo cp "$INSTALL_DIR/services/oi-web.service"   /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable oi-booth oi-web
sudo systemctl start oi-web

IP=$(hostname -I | awk '{print $1}')
echo ""
echo "============================================"
echo "  oi-booth installed successfully"
echo "============================================"
echo "  Admin panel:  http://$IP:5000/admin"
echo "  Gallery:      http://$IP:5000/gallery"
echo "  Start booth:  sudo systemctl start oi-booth"
echo "  Logs:         journalctl -u oi-booth -f"
echo "============================================"
