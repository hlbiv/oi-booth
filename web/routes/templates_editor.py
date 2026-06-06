"""
Template editor routes.
Templates are stored as JSON in config/templates/.
Applying a template writes the relevant keys to pibooth.cfg.
"""

import os
import json
import re
from pathlib import Path
from configparser import ConfigParser

from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash

try:
    from booth.ipc import send_command as _ipc_send
except ImportError:
    _ipc_send = None

templates_bp = Blueprint("templates", __name__)

TEMPLATES_DIR = Path(os.environ.get("OI_TEMPLATES_DIR",
    Path(__file__).parent.parent.parent / "config" / "templates"))

CONFIG_PATH = Path(os.environ.get("PIBOOTH_CFG",
    Path.home() / ".config/pibooth/pibooth.cfg"))

BACKGROUNDS_DIR = Path(os.environ.get("OI_BACKGROUNDS_DIR",
    Path.home() / ".config/pibooth/backgrounds"))

OVERLAYS_DIR = Path(os.environ.get("OI_OVERLAYS_DIR",
    Path.home() / ".config/pibooth/overlays"))


def _load_templates() -> list:
    TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
    templates = []
    for f in sorted(TEMPLATES_DIR.glob("*.json")):
        try:
            data = json.loads(f.read_text())
            data["_file"] = f.name
            templates.append(data)
        except Exception:
            pass
    return templates


def _save_template(name: str, data: dict) -> str:
    TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^a-z0-9_-]", "_", name.lower().strip())
    path = TEMPLATES_DIR / f"{slug}.json"
    data["name"] = name
    path.write_text(json.dumps(data, indent=2))
    return path.name


def _apply_template(data: dict):
    cfg = ConfigParser()
    if CONFIG_PATH.exists():
        cfg.read(CONFIG_PATH)

    def _set(section, key, value):
        if not cfg.has_section(section):
            cfg.add_section(section)
        cfg.set(section, key, str(value))

    _set("PICTURE", "orientation", data.get("orientation", "auto"))
    _set("PICTURE", "captures", f"({data.get('captures', 1)},)")
    _set("PICTURE", "margin_thick", str(data.get("margin", 0)))
    _set("PICTURE", "footer_text1", data.get("footer_text1", ""))
    _set("PICTURE", "footer_text2", data.get("footer_text2", ""))

    bg = data.get("background", "")
    _set("PICTURE", "backgrounds", bg)
    _set("WINDOW", "background", bg)

    overlay = data.get("overlay", "")
    _set("PICTURE", "overlays", overlay)

    text_color = data.get("text_color", "(255, 255, 255)")
    _set("PICTURE", "text_colors", f"{text_color}, {text_color}")

    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        cfg.write(f)


@templates_bp.route("/")
def index():
    templates = _load_templates()
    backgrounds = sorted(BACKGROUNDS_DIR.glob("*")) if BACKGROUNDS_DIR.exists() else []
    overlays = sorted(OVERLAYS_DIR.glob("*")) if OVERLAYS_DIR.exists() else []
    return render_template("admin/template_editor.html",
                           templates=templates,
                           backgrounds=backgrounds,
                           overlays=overlays)


@templates_bp.route("/save", methods=["POST"])
def save():
    data = request.get_json(force=True)
    name = data.get("name", "Untitled").strip()
    if not name:
        return jsonify({"ok": False, "error": "Name required"}), 400
    filename = _save_template(name, data)
    return jsonify({"ok": True, "file": filename})


@templates_bp.route("/load/<filename>")
def load(filename):
    path = TEMPLATES_DIR / Path(filename).name
    if not path.exists():
        return jsonify({"ok": False, "error": "Not found"}), 404
    return jsonify(json.loads(path.read_text()))


@templates_bp.route("/apply/<filename>", methods=["POST"])
def apply(filename):
    path = TEMPLATES_DIR / Path(filename).name
    if not path.exists():
        flash("Template not found.", "error")
        return redirect(url_for("templates.index"))
    data = json.loads(path.read_text())
    _apply_template(data)
    if _ipc_send:
        try:
            _ipc_send("restart")
        except Exception:
            pass
    flash(f"Template '{data.get('name')}' applied — pibooth is restarting.", "success")
    return redirect(url_for("templates.index"))


@templates_bp.route("/delete/<filename>", methods=["POST"])
def delete(filename):
    path = TEMPLATES_DIR / Path(filename).name
    if path.exists():
        path.unlink()
    return jsonify({"ok": True})


@templates_bp.route("/api/backgrounds")
def api_backgrounds():
    if BACKGROUNDS_DIR.exists():
        files = [f.name for f in sorted(BACKGROUNDS_DIR.glob("*"))]
    else:
        files = []
    return jsonify(files)


@templates_bp.route("/api/overlays")
def api_overlays():
    if OVERLAYS_DIR.exists():
        files = [f.name for f in sorted(OVERLAYS_DIR.glob("*"))]
    else:
        files = []
    return jsonify(files)
