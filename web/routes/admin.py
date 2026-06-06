"""
Admin panel routes.
Handles: config editor, background uploads, storage status, booth restart.
"""

import os
import shutil
import subprocess
from pathlib import Path
from configparser import ConfigParser

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, send_file

admin_bp = Blueprint("admin", __name__)

CONFIG_PATH = Path(os.environ.get("PIBOOTH_CFG", Path.home() / ".config/pibooth/pibooth.cfg"))
BACKGROUNDS_DIR = Path(os.environ.get("OI_BACKGROUNDS_DIR",
                        Path.home() / ".config/pibooth/backgrounds"))
OVERLAYS_DIR = Path(os.environ.get("OI_OVERLAYS_DIR",
                     Path.home() / ".config/pibooth/overlays"))
STORAGE_DIR = Path(os.environ.get("OI_STORAGE_DIR",
                    Path.home() / "Pictures/pibooth"))

ALLOWED_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif"}


def _read_config() -> ConfigParser:
    cfg = ConfigParser()
    if CONFIG_PATH.exists():
        cfg.read(CONFIG_PATH)
    return cfg


def _save_config(cfg: ConfigParser):
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        cfg.write(f)


def _storage_info():
    try:
        total, used, free = shutil.disk_usage(STORAGE_DIR)
        return {
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


@admin_bp.route("/")
def index():
    cfg = _read_config()
    storage = _storage_info()
    photo_count = _photo_count()
    backgrounds = sorted(BACKGROUNDS_DIR.glob("*")) if BACKGROUNDS_DIR.exists() else []
    overlays = sorted(OVERLAYS_DIR.glob("*")) if OVERLAYS_DIR.exists() else []
    return render_template(
        "admin/index.html",
        cfg=cfg,
        storage=storage,
        photo_count=photo_count,
        backgrounds=backgrounds,
        overlays=overlays,
    )


@admin_bp.route("/config", methods=["POST"])
def save_config():
    cfg = _read_config()
    section = request.form.get("section", "GENERAL")
    key = request.form.get("key", "").strip()
    value = request.form.get("value", "").strip()

    if not key:
        flash("Key cannot be empty.", "error")
        return redirect(url_for("admin.index"))

    if not cfg.has_section(section):
        cfg.add_section(section)
    cfg.set(section, key, value)
    _save_config(cfg)
    flash(f"Saved [{section}] {key} = {value}", "success")
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
        flash(f"Deleted background: {filename}", "success")
    return redirect(url_for("admin.index"))


@admin_bp.route("/delete/overlay/<filename>", methods=["POST"])
def delete_overlay(filename):
    target = OVERLAYS_DIR / Path(filename).name
    if target.exists() and target.is_file():
        target.unlink()
        flash(f"Deleted overlay: {filename}", "success")
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
            ["journalctl", "-u", "oi-booth", "-n", "100", "--no-pager"],
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
        "config_exists": CONFIG_PATH.exists(),
    })
