#!/bin/bash
# oi-booth installer — run once on the Pi as the pi user
set -e

INSTALL_DIR="$HOME/oi-booth"
VENV="$INSTALL_DIR/venv"
CFG_DIR="$HOME/.config/pibooth"

echo "==> Updating system packages"
sudo apt-get update -qq
sudo apt-get install -y \
  python3 python3-venv python3-pip \
  libsdl2-dev python3-opencv \
  cups libcups2-dev \
  network-manager \
  fonts-dejavu-core \
  git

echo "==> Creating virtualenv"
python3 -m venv "$VENV"
"$VENV/bin/pip" install --upgrade pip -q

echo "==> Installing Python dependencies"
"$VENV/bin/pip" install -r "$INSTALL_DIR/requirements.txt" -q

echo "==> Copying pibooth plugin"
PLUGIN_DIR="$CFG_DIR/plugins"
mkdir -p "$PLUGIN_DIR"
cp "$INSTALL_DIR/booth/plugin.py" "$PLUGIN_DIR/oi_booth_plugin.py"

echo "==> Copying booth support modules"
# Copy support modules into plugins/booth/ so 'from booth.ipc import ...' works
# when pibooth loads the plugin from this directory.
BOOTH_PKG="$PLUGIN_DIR/booth"
mkdir -p "$BOOTH_PKG"
for mod in ipc.py modes.py ai_bg.py attract.py events.py __init__.py; do
  src="$INSTALL_DIR/booth/$mod"
  [ -f "$src" ] && cp "$src" "$BOOTH_PKG/$mod"
done
touch "$BOOTH_PKG/__init__.py"

echo "==> Copying default config (if none exists)"
CFG="$CFG_DIR/pibooth.cfg"
if [ ! -f "$CFG" ]; then
  mkdir -p "$(dirname "$CFG")"
  cp "$INSTALL_DIR/config/pibooth.cfg" "$CFG"
  # Replace ~ plugin path with absolute path so pibooth always finds it
  PLUGIN_ABS="$PLUGIN_DIR/oi_booth_plugin.py"
  sed -i "s|~/.config/pibooth/plugins/oi_booth_plugin.py|$PLUGIN_ABS|" "$CFG"
  echo "    Wrote $CFG (plugin path: $PLUGIN_ABS)"
else
  echo "    Config already exists — skipping"
  echo "    Ensure [GENERAL] plugins = $PLUGIN_DIR/oi_booth_plugin.py"
fi

echo "==> Creating required directories"
mkdir -p "$CFG_DIR/backgrounds"
mkdir -p "$CFG_DIR/overlays"
mkdir -p "$CFG_DIR/attract"
mkdir -p "$CFG_DIR/events"
mkdir -p "$HOME/Pictures/pibooth"
mkdir -p "$INSTALL_DIR/config/templates"

echo "==> Setting up .env file"
ENV_FILE="$INSTALL_DIR/.env"
if [ ! -f "$ENV_FILE" ]; then
  cp "$INSTALL_DIR/.env.example" "$ENV_FILE"
  # Generate a random secret key
  SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
  sed -i "s/change-me-in-production/$SECRET/" "$ENV_FILE"
  echo "    Created $ENV_FILE"
  echo "    IMPORTANT: Edit $ENV_FILE to set OI_ADMIN_PIN and email settings"
else
  echo "    .env already exists — skipping"
fi

echo "==> Installing USB auto-mount udev rule"
sudo cp "$INSTALL_DIR/scripts/usb-mount.rules" /etc/udev/rules.d/99-oi-booth-usb.rules
sudo udevadm control --reload-rules

echo "==> Registering systemd services"
# Inject INSTALL_DIR into service files
sed "s|/home/pi/oi-booth|$INSTALL_DIR|g" \
  "$INSTALL_DIR/services/oi-booth.service" | sudo tee /etc/systemd/system/oi-booth.service > /dev/null
sed "s|/home/pi/oi-booth|$INSTALL_DIR|g" \
  "$INSTALL_DIR/services/oi-web.service" | sudo tee /etc/systemd/system/oi-web.service > /dev/null

sudo systemctl daemon-reload
sudo systemctl enable oi-booth oi-web
sudo systemctl start oi-web

IP=$(hostname -I | awk '{print $1}')
echo ""
echo "============================================"
echo "  oi-booth installed successfully!"
echo "============================================"
echo "  Admin panel: http://$IP:5000/admin"
echo "  Gallery:     http://$IP:5000/gallery"
echo ""
echo "  Default PIN: 1234  (change in .env → OI_ADMIN_PIN)"
echo "  Config:      $ENV_FILE"
echo ""
echo "  Start booth: sudo systemctl start oi-booth"
echo "  Web logs:    journalctl -u oi-web -f"
echo "  Booth logs:  journalctl -u oi-booth -f"
echo "============================================"
