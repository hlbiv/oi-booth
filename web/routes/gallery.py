"""
Gallery routes — user photo retrieval.
"""

import os
from pathlib import Path
from datetime import datetime

from flask import Blueprint, render_template, send_file, abort

gallery_bp = Blueprint("gallery", __name__)

STORAGE_DIR = Path(os.environ.get("OI_STORAGE_DIR",
                    Path.home() / "Pictures/pibooth"))

GIF_SUFFIXES = ("_animated.gif", "_boomerang.gif")


def _all_photos() -> list:
    """Return all photo/gif files sorted newest first."""
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
    # Strip known suffixes to get a clean session_id
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
    return render_template("gallery/session.html",
                           session_id=session_id,
                           filename=photo.name,
                           is_gif=meta["is_gif"],
                           taken_at=meta["taken_at"])


@gallery_bp.route("/<session_id>/photo")
def photo(session_id):
    p = _find_photo(session_id)
    if not p:
        abort(404)
    mime = "image/gif" if p.suffix == ".gif" else "image/jpeg"
    return send_file(p, mimetype=mime)


@gallery_bp.route("/")
def index():
    try:
        all_photos = _all_photos()[:48]
        photos = [_photo_meta(p) for p in all_photos]
    except Exception:
        photos = []
    return render_template("gallery/index.html", photos=photos)
