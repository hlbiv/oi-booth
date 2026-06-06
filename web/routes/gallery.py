"""
Gallery routes.
Users scan a QR code and land here to view and download their photos.
"""

import os
from pathlib import Path

from flask import Blueprint, render_template, send_file, abort

gallery_bp = Blueprint("gallery", __name__)

STORAGE_DIR = Path(os.environ.get("OI_STORAGE_DIR",
                    Path.home() / "Pictures/pibooth"))


def _find_photo(session_id: str) -> Path | None:
    # session_id is the stem of the filename e.g. 2026-06-06-12-00-00_pibooth
    # Try exact match first, then prefix match
    exact = STORAGE_DIR / f"{session_id}.jpg"
    if exact.exists():
        return exact
    matches = list(STORAGE_DIR.glob(f"{session_id}*.jpg"))
    return matches[0] if matches else None


@gallery_bp.route("/<session_id>")
def session(session_id):
    photo = _find_photo(session_id)
    if not photo:
        return render_template("gallery/not_found.html", session_id=session_id), 404
    return render_template("gallery/session.html", session_id=session_id,
                           filename=photo.name)


@gallery_bp.route("/<session_id>/photo")
def photo(session_id):
    photo = _find_photo(session_id)
    if not photo:
        abort(404)
    return send_file(photo, mimetype="image/jpeg")


@gallery_bp.route("/")
def index():
    try:
        photos = sorted(STORAGE_DIR.glob("*_pibooth.jpg"), reverse=True)[:20]
    except Exception:
        photos = []
    return render_template("gallery/index.html", photos=photos)
