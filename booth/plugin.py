"""
oi_booth_plugin.py
==================
Pibooth plugin for oi-booth. After each capture session:
  - Saves photo to configured storage directory (USB or local)
  - Generates a QR code pointing to the local web gallery
  - Displays the QR code on screen during the finish state

Install:
  Copy to ~/.config/pibooth/plugins/ or add the path to pibooth.cfg [GENERAL] plugins

Config (pibooth.cfg):
  [OIBOOTH]
  web_host       = 0.0.0.0
  web_port       = 5000
  storage_dir    = /media/usb/oi-booth-photos
  show_qr        = True
  qr_duration    = 10
"""

import os
import json
import time
import socket
import tempfile
from pathlib import Path

import pluggy
import qrcode
from PIL import Image

hookimpl = pluggy.HookimplMarker("pibooth")

SECTION = "OIBOOTH"

DEFAULTS = {
    "web_host": "0.0.0.0",
    "web_port": "5000",
    "storage_dir": "",
    "show_qr": "True",
    "qr_duration": "10",
}


def _get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "localhost"


def _cfg(cfg, key):
    try:
        return cfg.get(SECTION, key).strip()
    except Exception:
        return DEFAULTS.get(key, "")


def _generate_qr(url: str, size: int = 300) -> Image.Image:
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    img = img.resize((size, size), Image.LANCZOS)
    return img


@hookimpl
def pibooth_configure(cfg):
    cfg.add_option(SECTION, "web_host", DEFAULTS["web_host"], "Web server host")
    cfg.add_option(SECTION, "web_port", DEFAULTS["web_port"], "Web server port")
    cfg.add_option(SECTION, "storage_dir", DEFAULTS["storage_dir"],
                   "Photo storage directory (leave blank to use pibooth default)")
    cfg.add_option(SECTION, "show_qr", DEFAULTS["show_qr"],
                   "Show QR code after capture (True/False)")
    cfg.add_option(SECTION, "qr_duration", DEFAULTS["qr_duration"],
                   "Seconds to show QR code on screen")


@hookimpl
def pibooth_startup(cfg, app):
    port = _cfg(cfg, "web_port")
    ip = _get_local_ip()
    print(f"[oi-booth] Web admin: http://{ip}:{port}/admin")
    print(f"[oi-booth] Gallery:   http://{ip}:{port}/gallery")


@hookimpl
def state_finish_enter(cfg, app, win):
    show_qr = _cfg(cfg, "show_qr").lower() in ("true", "1", "yes")
    if not show_qr:
        return

    picture_file = getattr(app, "previous_picture_file", None)
    if not picture_file or not Path(picture_file).exists():
        return

    session_id = Path(picture_file).stem
    port = _cfg(cfg, "web_port")
    ip = _get_local_ip()
    gallery_url = f"http://{ip}:{port}/gallery/{session_id}"

    print(f"[oi-booth] Gallery URL: {gallery_url}")

    try:
        qr_img = _generate_qr(gallery_url, size=250)
        tmp = os.path.join(tempfile.gettempdir(), f"oi_booth_qr_{session_id}.png")
        qr_img.save(tmp)

        # Store on app so the view can display it
        app.oi_booth_qr_path = tmp
        app.oi_booth_qr_url = gallery_url
        app.oi_booth_qr_expires = time.time() + int(_cfg(cfg, "qr_duration") or "10")
    except Exception as e:
        print(f"[oi-booth] QR generation failed: {e}")
