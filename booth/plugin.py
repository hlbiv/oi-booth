"""
oi_booth_plugin.py
==================
Pibooth plugin for oi-booth. Provides:
  - QR code overlay on display after each session
  - GIF / Boomerang capture modes
  - AI background removal (Pi 4+ only)
  - IPC bridge for the CoPilot web remote

Install:
  Copy to ~/.config/pibooth/plugins/ or set path in [GENERAL] plugins

Config (pibooth.cfg):
  [OIBOOTH]
  web_host          = 0.0.0.0
  web_port          = 5000
  storage_dir       =
  show_qr           = True
  qr_duration       = 12
  mode              = photo        # photo | gif | boomerang
  gif_fps           = 8
  gif_frames        = 4
  ai_background     = False
  ai_bg_image       =             # path to a background image for AI removal
"""

import os
import time
import socket
import tempfile
from pathlib import Path

import pluggy
import qrcode
from PIL import Image, ImageDraw, ImageFont

# Local helpers (relative imports work when run as a plugin from same package,
# fallback to sys.path when copied standalone)
try:
    from booth.ipc import read_command, write_status
    from booth.modes import make_gif, make_boomerang, output_path_for
    from booth.ai_bg import remove_background, load_background, AI_BG_SUPPORTED
except ImportError:
    import sys, os as _os
    sys.path.insert(0, _os.path.join(_os.path.dirname(__file__), '..'))
    from booth.ipc import read_command, write_status
    from booth.modes import make_gif, make_boomerang, output_path_for
    from booth.ai_bg import remove_background, load_background, AI_BG_SUPPORTED

hookimpl = pluggy.HookimplMarker("pibooth")

SECTION = "OIBOOTH"
DEFAULTS = {
    "web_host": "0.0.0.0",
    "web_port": "5000",
    "storage_dir": "",
    "show_qr": "True",
    "qr_duration": "12",
    "mode": "photo",
    "gif_fps": "8",
    "gif_frames": "4",
    "ai_background": "False",
    "ai_bg_image": "",
}

_qr_state = {
    "active": False,
    "surface": None,
    "expires_at": 0.0,
    "url": "",
}

# Track photo count across sessions
_photo_count = 0
_current_state = "wait"
_current_mode = "photo"
_last_session_id = ""


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


def _bool(val: str) -> bool:
    return val.lower() in ("true", "1", "yes")


def _build_qr_surface(url: str, win_size: tuple):
    import pygame

    qr = qrcode.QRCode(version=1,
                       error_correction=qrcode.constants.ERROR_CORRECT_M,
                       box_size=8, border=3)
    qr.add_data(url)
    qr.make(fit=True)
    qr_pil = qr.make_image(fill_color="black", back_color="white").convert("RGB")

    qr_size = min(280, int(win_size[1] * 0.38))
    qr_pil = qr_pil.resize((qr_size, qr_size), Image.LANCZOS)

    pad = 24
    label = "Scan to get your photo"
    panel_w = qr_size + pad * 2
    panel_h = qr_size + 64 + pad * 2

    panel = Image.new("RGBA", (panel_w, panel_h), (10, 10, 10, 220))
    draw = ImageDraw.Draw(panel)

    try:
        font_label = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 18)
        font_url = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 13)
    except Exception:
        font_label = ImageFont.load_default()
        font_url = font_label

    bbox = draw.textbbox((0, 0), label, font=font_label)
    lw = bbox[2] - bbox[0]
    draw.text(((panel_w - lw) // 2, pad // 2), label,
              font=font_label, fill=(255, 255, 255, 255))
    panel.paste(qr_pil, (pad, 36))

    short_url = url.replace("http://", "")
    bbox2 = draw.textbbox((0, 0), short_url, font=font_url)
    uw = bbox2[2] - bbox2[0]
    draw.text(((panel_w - uw) // 2, 36 + qr_size + 8), short_url,
              font=font_url, fill=(180, 180, 180, 255))

    pg_surface = pygame.image.fromstring(
        panel.tobytes(), panel.size, "RGBA").convert_alpha()

    overlay = pygame.Surface(win_size, pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 160))
    cx = (win_size[0] - panel_w) // 2
    cy = (win_size[1] - panel_h) // 2
    overlay.blit(pg_surface, (cx, cy))
    return overlay


# ── Plugin hooks ──────────────────────────────────────────────────────────────

@hookimpl
def pibooth_configure(cfg):
    cfg.add_option(SECTION, "web_host",      DEFAULTS["web_host"],      "Web server host")
    cfg.add_option(SECTION, "web_port",      DEFAULTS["web_port"],      "Web server port")
    cfg.add_option(SECTION, "storage_dir",   DEFAULTS["storage_dir"],   "Photo storage directory")
    cfg.add_option(SECTION, "show_qr",       DEFAULTS["show_qr"],       "Show QR after capture")
    cfg.add_option(SECTION, "qr_duration",   DEFAULTS["qr_duration"],   "QR display seconds")
    cfg.add_option(SECTION, "mode",          DEFAULTS["mode"],          "Capture mode: photo|gif|boomerang")
    cfg.add_option(SECTION, "gif_fps",       DEFAULTS["gif_fps"],       "GIF frames per second")
    cfg.add_option(SECTION, "gif_frames",    DEFAULTS["gif_frames"],    "Number of frames for GIF/boomerang")
    cfg.add_option(SECTION, "ai_background", DEFAULTS["ai_background"], "AI background removal (Pi 4+ only)")
    cfg.add_option(SECTION, "ai_bg_image",   DEFAULTS["ai_bg_image"],   "Background image for AI removal")


@hookimpl
def pibooth_startup(cfg, app):
    global _current_mode
    port = _cfg(cfg, "web_port")
    ip = _get_local_ip()
    _current_mode = _cfg(cfg, "mode") or "photo"

    print(f"[oi-booth] Web admin: http://{ip}:{port}/admin")
    print(f"[oi-booth] CoPilot:   http://{ip}:{port}/admin/copilot")
    print(f"[oi-booth] Gallery:   http://{ip}:{port}/gallery")
    print(f"[oi-booth] Mode:      {_current_mode}")
    if AI_BG_SUPPORTED:
        print(f"[oi-booth] AI backgrounds: enabled")
    else:
        print(f"[oi-booth] AI backgrounds: disabled (Pi 4+ required)")

    storage = _cfg(cfg, "storage_dir")
    if storage:
        Path(storage).mkdir(parents=True, exist_ok=True)

    write_status("wait", mode=_current_mode)


@hookimpl
def state_wait_do(cfg, app, win, events):
    """Poll for CoPilot commands while the booth is idle."""
    global _current_mode, _current_state
    _current_state = "wait"
    write_status("wait", mode=_current_mode, photo_count=_photo_count,
                 last_session_id=_last_session_id)

    cmd = read_command()
    if not cmd:
        return

    action = cmd.get("action")
    print(f"[oi-booth] CoPilot command: {action}")

    if action == "set_mode":
        new_mode = cmd.get("mode", "photo")
        if new_mode in ("photo", "gif", "boomerang"):
            _current_mode = new_mode
            print(f"[oi-booth] Mode changed to: {_current_mode}")

    elif action == "capture":
        import pygame
        pygame.event.post(pygame.event.Event(
            pygame.KEYDOWN, key=pygame.K_p, mod=0, unicode="p"))

    elif action == "restart":
        import subprocess
        subprocess.Popen(["sudo", "systemctl", "restart", "oi-booth"])


@hookimpl
def state_capture_enter(cfg, app, win):
    global _current_state
    _current_state = "capture"
    write_status("capture", mode=_current_mode, photo_count=_photo_count)

    # For GIF/boomerang, override captures count to gif_frames
    mode = _cfg(cfg, "mode") or _current_mode
    if mode in ("gif", "boomerang"):
        frames = int(_cfg(cfg, "gif_frames") or "4")
        app.capture_nbr = frames


@hookimpl
def state_processing_enter(cfg, app, win):
    global _photo_count, _last_session_id, _current_state
    _current_state = "processing"
    write_status("processing", mode=_current_mode, photo_count=_photo_count)

    mode = _cfg(cfg, "mode") or _current_mode

    # AI background removal
    if _bool(_cfg(cfg, "ai_background")) and AI_BG_SUPPORTED:
        bg_path = _cfg(cfg, "ai_bg_image")
        bg_image = load_background(bg_path) if bg_path else None
        captures = getattr(app, "capture_date", [])
        if captures:
            try:
                raw_dir = Path(cfg.getpath("GENERAL", "directory")) / "raw"
                # Find the most recent raw capture files
                recent = sorted(raw_dir.glob("**/*.jpg"),
                                key=lambda p: p.stat().st_mtime,
                                reverse=True)[:len(captures)]
                for raw_file in recent:
                    img = Image.open(raw_file)
                    result = remove_background(img, bg_image)
                    result.save(raw_file)
                print(f"[oi-booth] AI background applied to {len(recent)} captures")
            except Exception as e:
                print(f"[oi-booth] AI background error: {e}")

    # GIF / Boomerang assembly
    if mode in ("gif", "boomerang"):
        _assemble_gif(cfg, app, mode)


def _assemble_gif(cfg, app, mode: str):
    """Build a GIF from the raw captures after processing."""
    global _photo_count, _last_session_id
    try:
        output_dir = Path(cfg.getpath("GENERAL", "directory"))
        raw_dir = output_dir / "raw"
        fps = int(_cfg(cfg, "gif_fps") or "8")

        # Find latest raw session folder
        sessions = sorted(raw_dir.glob("*/"), key=lambda p: p.stat().st_mtime,
                          reverse=True)
        if not sessions:
            return

        latest_session = sessions[0]
        jpegs = sorted(latest_session.glob("*.jpg"), key=lambda p: p.stat().st_mtime)
        if not jpegs:
            return

        captures = [Image.open(j) for j in jpegs]
        timestamp = latest_session.name
        suffix = "_boomerang.gif" if mode == "boomerang" else "_animated.gif"
        out_path = str(output_dir / f"{timestamp}{suffix}")

        if mode == "boomerang":
            make_boomerang(captures, out_path, fps=fps)
        else:
            make_gif(captures, out_path, fps=fps)

        app.previous_picture_file = out_path
        _photo_count += 1
        _last_session_id = Path(out_path).stem
        print(f"[oi-booth] {mode.capitalize()} saved: {out_path}")

    except Exception as e:
        print(f"[oi-booth] GIF assembly error: {e}")


@hookimpl
def state_finish_enter(cfg, app, win):
    global _photo_count, _last_session_id, _current_state, _qr_state
    _current_state = "finish"

    picture_file = getattr(app, "previous_picture_file", None)
    if picture_file and Path(picture_file).exists():
        mode = _cfg(cfg, "mode") or _current_mode
        if mode == "photo":
            _photo_count += 1
        _last_session_id = Path(picture_file).stem

    write_status("finish", mode=_current_mode, photo_count=_photo_count,
                 last_session_id=_last_session_id)

    if not _bool(_cfg(cfg, "show_qr")):
        return
    if not picture_file or not Path(picture_file).exists():
        return

    port = _cfg(cfg, "web_port")
    ip = _get_local_ip()
    gallery_url = f"http://{ip}:{port}/gallery/{_last_session_id}"
    duration = int(_cfg(cfg, "qr_duration") or "12")
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

    if _qr_state["surface"]:
        try:
            win.surface.blit(_qr_state["surface"], (0, 0))
            pygame.display.update()
        except Exception:
            pass


@hookimpl
def state_finish_exit(cfg, app, win):
    global _qr_state, _current_state
    _current_state = "wait"
    _qr_state["active"] = False
    _qr_state["surface"] = None
