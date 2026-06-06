"""
Gallery routes — public photo retrieval.
"""

import os
from pathlib import Path
from datetime import datetime

import subprocess
import re

from flask import Blueprint, render_template, send_file, abort, jsonify

gallery_bp = Blueprint("gallery", __name__)

STORAGE_DIR = Path(os.environ.get("OI_STORAGE_DIR",
                    Path.home() / "Pictures/pibooth"))


def _active_event() -> dict | None:
    """Return the currently-active event dict, or None."""
    try:
        from booth.events import get_active_event
        return get_active_event()
    except Exception:
        return None


def _all_photos() -> list:
    items = []
    for pattern in ("*_pibooth.jpg", "*_animated.gif", "*_boomerang.gif"):
        items.extend(STORAGE_DIR.glob(pattern))
    return sorted(items, key=lambda p: p.stat().st_mtime, reverse=True)


def _find_photo(session_id: str) -> Path | None:
    for suffix in ("_pibooth.jpg", "_animated.gif", "_boomerang.gif", ".jpg", ".gif"):
        p = STORAGE_DIR / f"{session_id}{suffix}"
        if p.exists():
            return p
    matches = list(STORAGE_DIR.glob(f"{session_id}*"))
    return matches[0] if matches else None


def _photo_meta(p: Path) -> dict:
    is_gif = p.suffix == ".gif"
    try:
        ts = p.stat().st_mtime
        taken_at = datetime.fromtimestamp(ts).strftime("%B %d, %Y · %I:%M %p")
    except Exception:
        taken_at = ""
    stem = p.stem
    for suf in ("_pibooth", "_animated", "_boomerang"):
        stem = stem.replace(suf, "")
    return {
        "session_id": p.stem,
        "filename": p.name,
        "is_gif": is_gif,
        "taken_at": taken_at,
        "clean_id": stem,
    }


@gallery_bp.route("/<session_id>")
def session(session_id):
    photo = _find_photo(session_id)
    if not photo:
        return render_template("gallery/not_found.html", session_id=session_id), 404
    meta = _photo_meta(photo)
    event = _active_event()
    return render_template("gallery/session.html",
                           session_id=session_id,
                           filename=photo.name,
                           is_gif=meta["is_gif"],
                           taken_at=meta["taken_at"],
                           event=event)


@gallery_bp.route("/<session_id>/photo")
def photo(session_id):
    p = _find_photo(session_id)
    if not p:
        abort(404)
    mime = "image/gif" if p.suffix == ".gif" else "image/jpeg"
    return send_file(p, mimetype=mime)


@gallery_bp.route("/<session_id>/print", methods=["POST"])
def print_photo(session_id):
    p = _find_photo(session_id)
    if not p:
        return jsonify({"ok": False, "error": "Photo not found"}), 404
    try:
        result = subprocess.run(
            ["lp", str(p)],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            m = re.search(r"request id is (\S+)", result.stdout)
            job_id = m.group(1) if m else "unknown"
            return jsonify({"ok": True, "job_id": job_id})
        return jsonify({"ok": False, "error": result.stderr.strip() or "Print failed"}), 500
    except FileNotFoundError:
        return jsonify({"ok": False, "error": "Printer not available"}), 503
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@gallery_bp.route("/")
def index():
    try:
        all_photos = _all_photos()[:48]
        photos = [_photo_meta(p) for p in all_photos]
    except Exception:
        photos = []
    event = _active_event()
    return render_template("gallery/index.html", photos=photos, event=event)
