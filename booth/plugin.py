"""
oi_booth_plugin.py
==================
Pibooth plugin for oi-booth.

After each capture session:
  - Saves photo to configured storage directory (USB or local)
  - Generates a QR code pointing to the local web gallery
  - Renders the QR + gallery URL as an overlay on the pibooth display
    during the finish state, then auto-dismisses

Install:
  Copy to ~/.config/pibooth/plugins/ or set path in pibooth.cfg [GENERAL] plugins

Config (pibooth.cfg):
  [OIBOOTH]
  web_host       = 0.0.0.0
  web_port       = 5000
  storage_dir    = /media/usb/oi-booth-photos
  show_qr        = True
  qr_duration    = 10
"""

import os
import time
import socket
import tempfile
from pathlib import Path

import pluggy
import qrcode
from PIL import Image, ImageDraw, ImageFont

hookimpl = pluggy.HookimplMarker("pibooth")

SECTION = "OIBOOTH"

DEFAULTS = {
    "web_host": "0.0.0.0",
    "web_port": "5000",
    "storage_dir": "",
    "show_qr": "True",
    "qr_duration": "10",
}

# Module-level state for the QR overlay
_qr_state = {
    "active": False,
    "surface": None,     # pygame.Surface when active
    "expires_at": 0.0,
    "url": "",
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


def _build_qr_surface(url: str, win_size: tuple) -> "pygame.Surface":
    """
    Build a pygame Surface containing a semi-transparent overlay with
    the QR code and gallery URL centred on screen.
    """
    import pygame

    # Generate QR image via Pillow
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=8,
        border=3,
    )
    qr.add_data(url)
    qr.make(fit=True)
    qr_pil = qr.make_image(fill_color="black", back_color="white").convert("RGB")

    # Size the QR relative to screen (max 280px on a Pi screen)
    qr_size = min(280, int(win_size[1] * 0.38))
    qr_pil = qr_pil.resize((qr_size, qr_size), Image.LANCZOS)

    # Panel dimensions
    pad = 24
    label = "Scan to get your photo"
    panel_w = qr_size + pad * 2
    panel_h = qr_size + 64 + pad * 2

    # Build panel as Pillow image (easier text rendering)
    panel = Image.new("RGBA", (panel_w, panel_h), (10, 10, 10, 220))
    draw = ImageDraw.Draw(panel)

    # Try to load a font, fall back gracefully
    try:
        font_label = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 18)
        font_url = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 13)
    except Exception:
        font_label = ImageFont.load_default()
        font_url = font_label

    # Label at top
    bbox = draw.textbbox((0, 0), label, font=font_label)
    lw = bbox[2] - bbox[0]
    draw.text(((panel_w - lw) // 2, pad // 2), label, font=font_label, fill=(255, 255, 255, 255))

    # Paste QR
    panel.paste(qr_pil, (pad, 36))

    # URL below QR
    short_url = url.replace("http://", "")
    bbox2 = draw.textbbox((0, 0), short_url, font=font_url)
    uw = bbox2[2] - bbox2[0]
    draw.text(((panel_w - uw) // 2, 36 + qr_size + 8), short_url, font=font_url, fill=(180, 180, 180, 255))

    # Convert to pygame surface
    panel_str = panel.tobytes()
    pg_surface = pygame.image.fromstring(panel_str, panel.size, "RGBA").convert_alpha()

    # Create full-screen semi-transparent backdrop
    overlay = pygame.Surface(win_size, pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 160))

    # Centre the panel on the overlay
    cx = (win_size[0] - panel_w) // 2
    cy = (win_size[1] - panel_h) // 2
    overlay.blit(pg_surface, (cx, cy))

    return overlay


# ── Plugin hooks ─────────────────────────────────────────────────────────────

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

    storage = _cfg(cfg, "storage_dir")
    if storage:
        Path(storage).mkdir(parents=True, exist_ok=True)
        print(f"[oi-booth] Storage:   {storage}")


@hookimpl
def state_finish_enter(cfg, app, win):
    global _qr_state
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
    duration = int(_cfg(cfg, "qr_duration") or "10")

    print(f"[oi-booth] Gallery URL: {gallery_url}")

    try:
        import pygame
        win_size = win.get_rect().size if hasattr(win, "get_rect") else (800, 600)
        surface = _build_qr_surface(gallery_url, win_size)
        _qr_state.update({
            "active": True,
            "surface": surface,
            "expires_at": time.time() + duration,
            "url": gallery_url,
        })
        app.oi_booth_qr_url = gallery_url
    except Exception as e:
        print(f"[oi-booth] QR overlay error: {e}")


@hookimpl
def state_finish_do(cfg, app, win, events):
    global _qr_state
    if not _qr_state["active"]:
        return

    # Dismiss on button press or expiry
    import pygame
    expired = time.time() >= _qr_state["expires_at"]
    btn_pressed = any(
        e.type == pygame.KEYDOWN or
        (hasattr(pygame, "FINGERUP") and e.type == pygame.FINGERUP)
        for e in events
    )

    if expired or btn_pressed:
        _qr_state["active"] = False
        _qr_state["surface"] = None
        return

    # Blit overlay on top of the current window surface
    if _qr_state["surface"]:
        try:
            win.surface.blit(_qr_state["surface"], (0, 0))
            pygame.display.update()
        except Exception:
            pass


@hookimpl
def state_finish_exit(cfg, app, win):
    global _qr_state
    _qr_state["active"] = False
    _qr_state["surface"] = None
