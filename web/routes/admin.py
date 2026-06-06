"""
Admin panel routes.
Handles: config editor, background uploads, storage status, booth restart, USB detection.
"""

import os
import re
import shutil
import subprocess
from pathlib import Path
from configparser import ConfigParser

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, send_file
from .auth import require_pin

admin_bp = Blueprint("admin", __name__)

CONFIG_PATH = Path(os.environ.get("PIBOOTH_CFG", Path.home() / ".config/pibooth/pibooth.cfg"))
BACKGROUNDS_DIR = Path(os.environ.get("OI_BACKGROUNDS_DIR",
                        Path.home() / ".config/pibooth/backgrounds"))
OVERLAYS_DIR = Path(os.environ.get("OI_OVERLAYS_DIR",
                     Path.home() / ".config/pibooth/overlays"))
STORAGE_DIR = Path(os.environ.get("OI_STORAGE_DIR",
                    Path.home() / "Pictures/pibooth"))

ALLOWED_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif"}

# Friendly labels for well-known config keys
KEY_LABELS = {
    "GENERAL": {
        "language": "Language",
        "directory": "Photo save directory",
        "autostart": "Autostart on boot",
        "debug": "Debug mode",
        "plugins": "Plugin paths",
    },
    "WINDOW": {
        "size": "Display size (or 'fullscreen')",
        "background": "Background color/image",
        "flash": "Flash on capture",
        "animate": "Animate captures",
        "preview_delay": "Preview countdown (seconds)",
        "preview_countdown": "Show countdown timer",
        "finish_picture_delay": "Show photo after capture (seconds)",
        "wait_picture_delay": "Show photo in wait screen (seconds)",
    },
    "PICTURE": {
        "orientation": "Orientation (auto/portrait/landscape)",
        "captures": "Capture count options",
        "captures_effects": "Capture effects",
        "margin_thick": "Border thickness (px)",
        "footer_text1": "Footer line 1",
        "footer_text2": "Footer line 2",
        "overlays": "Overlay images",
        "backgrounds": "Background images",
    },
    "CAMERA": {
        "iso": "ISO sensitivity",
        "flip": "Horizontal flip",
        "rotation": "Rotation (0/90/180/270)",
        "resolution": "Capture resolution",
    },
    "PRINTER": {
        "printer_name": "Printer name (CUPS)",
        "printer_delay": "Print screen duration (seconds)",
        "auto_print": "Auto-print copies",
        "max_duplicates": "Max duplicate prints",
    },
    "OIBOOTH": {
        "web_host": "Web server host",
        "web_port": "Web server port",
        "storage_dir": "Photo storage directory",
        "show_qr": "Show QR after capture",
        "qr_duration": "QR display duration (seconds)",
    },
}


def _read_config() -> ConfigParser:
    cfg = ConfigParser()
    if CONFIG_PATH.exists():
        cfg.read(CONFIG_PATH)
    return cfg


def _save_config(cfg: ConfigParser):
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        cfg.write(f)


def _storage_info(path: Path = None):
    target = path or STORAGE_DIR
    try:
        total, used, free = shutil.disk_usage(target)
        return {
            "path": str(target),
            "total_gb": round(total / 1e9, 1),
            "used_gb": round(used / 1e9, 1),
            "free_gb": round(free / 1e9, 1),
            "used_pct": round(used / total * 100),
        }
    except Exception:
        return None


def _photo_count():
    try:
        return len(list(STORAGE_DIR.glob("*_pibooth.jpg")))
    except Exception:
        return 0


def _detect_usb_drives():
    """Return list of mounted USB drives with label, mount point, and disk usage."""
    drives = []
    try:
        result = subprocess.run(
            ["lsblk", "-J", "-o", "NAME,MOUNTPOINT,LABEL,HOTPLUG,FSTYPE,SIZE"],
            capture_output=True, text=True, timeout=5
        )
        import json as _json
        data = _json.loads(result.stdout)
        for dev in data.get("blockdevices", []):
            for child in dev.get("children", []):
                mp = child.get("mountpoint")
                hotplug = child.get("hotplug")
                if mp and hotplug:
                    info = _storage_info(Path(mp))
                    drives.append({
                        "name": child.get("name"),
                        "label": child.get("label") or child.get("name"),
                        "mountpoint": mp,
                        "size": child.get("size"),
                        "fstype": child.get("fstype"),
                        "storage": info,
                    })
    except Exception:
        # lsblk not available (dev machine) — skip
        pass
    return drives


@admin_bp.route("/")
def index():
    cfg = _read_config()
    storage = _storage_info()
    photo_count = _photo_count()
    usb_drives = _detect_usb_drives()
    backgrounds = sorted(BACKGROUNDS_DIR.glob("*")) if BACKGROUNDS_DIR.exists() else []
    overlays = sorted(OVERLAYS_DIR.glob("*")) if OVERLAYS_DIR.exists() else []

    # Build structured config for display/editing
    sections = {}
    for section in cfg.sections():
        sections[section] = {
            key: {
                "value": value,
                "label": KEY_LABELS.get(section, {}).get(key, key.replace("_", " ").title()),
            }
            for key, value in cfg.items(section)
        }
    # Always show OIBOOTH even if not yet in file
    if "OIBOOTH" not in sections:
        sections["OIBOOTH"] = {
            k: {"value": "", "label": v}
            for k, v in KEY_LABELS["OIBOOTH"].items()
        }

    return render_template(
        "admin/index.html",
        cfg=cfg,
        sections=sections,
        storage=storage,
        photo_count=photo_count,
        usb_drives=usb_drives,
        backgrounds=backgrounds,
        overlays=overlays,
    )


@admin_bp.route("/config", methods=["POST"])
def save_config():
    cfg = _read_config()
    updates = {}

    # Collect all section/key/value triples from the form
    # Form fields are named like: cfg[GENERAL][language]
    pattern = re.compile(r"^cfg\[([A-Z0-9_]+)\]\[([a-z0-9_]+)\]$")
    for field, value in request.form.items():
        m = pattern.match(field)
        if m:
            section, key = m.group(1), m.group(2)
            updates.setdefault(section, {})[key] = value.strip()

    for section, keys in updates.items():
        if not cfg.has_section(section):
            cfg.add_section(section)
        for key, value in keys.items():
            cfg.set(section, key, value)

    _save_config(cfg)
    flash("Configuration saved.", "success")
    return redirect(url_for("admin.index"))


@admin_bp.route("/config/set", methods=["POST"])
def set_one():
    """Quick single-key update (used by inline edit forms)."""
    cfg = _read_config()
    section = request.form.get("section", "").strip().upper()
    key = request.form.get("key", "").strip().lower()
    value = request.form.get("value", "").strip()

    if not section or not key:
        flash("Section and key are required.", "error")
        return redirect(url_for("admin.index"))

    if not cfg.has_section(section):
        cfg.add_section(section)
    cfg.set(section, key, value)
    _save_config(cfg)
    flash(f"Saved [{section}] {key}", "success")
    return redirect(url_for("admin.index"))


@admin_bp.route("/storage/set-usb", methods=["POST"])
def set_usb_storage():
    """Point photo storage to a detected USB drive."""
    mountpoint = request.form.get("mountpoint", "").strip()
    if not mountpoint or not Path(mountpoint).exists():
        flash("Invalid mount point.", "error")
        return redirect(url_for("admin.index"))

    cfg = _read_config()
    photo_dir = str(Path(mountpoint) / "oi-booth-photos")
    Path(photo_dir).mkdir(parents=True, exist_ok=True)

    if not cfg.has_section("GENERAL"):
        cfg.add_section("GENERAL")
    cfg.set("GENERAL", "directory", photo_dir)

    if not cfg.has_section("OIBOOTH"):
        cfg.add_section("OIBOOTH")
    cfg.set("OIBOOTH", "storage_dir", photo_dir)

    _save_config(cfg)
    flash(f"Storage set to {photo_dir}", "success")
    return redirect(url_for("admin.index"))


@admin_bp.route("/upload/background", methods=["POST"])
def upload_background():
    file = request.files.get("file")
    if not file or not file.filename:
        flash("No file selected.", "error")
        return redirect(url_for("admin.index"))
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_IMAGE_EXTS:
        flash(f"Invalid file type: {ext}", "error")
        return redirect(url_for("admin.index"))
    BACKGROUNDS_DIR.mkdir(parents=True, exist_ok=True)
    dest = BACKGROUNDS_DIR / Path(file.filename).name
    file.save(dest)
    flash(f"Background uploaded: {dest.name}", "success")
    return redirect(url_for("admin.index"))


@admin_bp.route("/upload/overlay", methods=["POST"])
def upload_overlay():
    file = request.files.get("file")
    if not file or not file.filename:
        flash("No file selected.", "error")
        return redirect(url_for("admin.index"))
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_IMAGE_EXTS:
        flash(f"Invalid file type: {ext}", "error")
        return redirect(url_for("admin.index"))
    OVERLAYS_DIR.mkdir(parents=True, exist_ok=True)
    dest = OVERLAYS_DIR / Path(file.filename).name
    file.save(dest)
    flash(f"Overlay uploaded: {dest.name}", "success")
    return redirect(url_for("admin.index"))


@admin_bp.route("/delete/background/<filename>", methods=["POST"])
def delete_background(filename):
    target = BACKGROUNDS_DIR / Path(filename).name
    if target.exists() and target.is_file():
        target.unlink()
        flash(f"Deleted: {filename}", "success")
    return redirect(url_for("admin.index"))


@admin_bp.route("/delete/overlay/<filename>", methods=["POST"])
def delete_overlay(filename):
    target = OVERLAYS_DIR / Path(filename).name
    if target.exists() and target.is_file():
        target.unlink()
        flash(f"Deleted: {filename}", "success")
    return redirect(url_for("admin.index"))


@admin_bp.route("/asset/<kind>/<filename>")
def serve_asset(kind, filename):
    if kind == "background":
        path = BACKGROUNDS_DIR / Path(filename).name
    elif kind == "overlay":
        path = OVERLAYS_DIR / Path(filename).name
    else:
        return "Not found", 404
    if path.exists():
        return send_file(path)
    return "Not found", 404


@admin_bp.route("/restart", methods=["POST"])
def restart_booth():
    try:
        subprocess.Popen(["sudo", "systemctl", "restart", "oi-booth"])
        flash("Booth restarting...", "success")
    except Exception as e:
        flash(f"Restart failed: {e}", "error")
    return redirect(url_for("admin.index"))


@admin_bp.route("/logs")
def logs():
    try:
        result = subprocess.run(
            ["journalctl", "-u", "oi-booth", "-n", "150", "--no-pager"],
            capture_output=True, text=True, timeout=5
        )
        lines = result.stdout.strip().split("\n") if result.stdout else []
    except Exception:
        lines = ["Log unavailable — journalctl not found or service not running."]
    return render_template("admin/logs.html", lines=lines)


@admin_bp.route("/api/status")
def api_status():
    return jsonify({
        "ok": True,
        "storage": _storage_info(),
        "photo_count": _photo_count(),
        "usb_drives": _detect_usb_drives(),
        "config_exists": CONFIG_PATH.exists(),
    })
