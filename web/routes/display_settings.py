"""
Display settings routes.
Handles: attract slideshow image upload/delete/serve, finish screen preview.
"""

import os
from pathlib import Path

from flask import (Blueprint, render_template, request, redirect,
                   url_for, flash, send_file)

display_bp = Blueprint("display", __name__)

ATTRACT_DIR = Path(os.environ.get("OI_ATTRACT_DIR",
                    Path.home() / ".config/pibooth/attract"))

ALLOWED_IMAGE_EXTS = {".jpg", ".jpeg", ".png"}


def _list_attract_images() -> list:
    """Return a sorted list of Path objects in the attract directory."""
    if not ATTRACT_DIR.exists():
        return []
    return sorted(
        p for p in ATTRACT_DIR.iterdir()
        if p.is_file() and p.suffix.lower() in ALLOWED_IMAGE_EXTS
    )


@display_bp.route("/")
def index():
    images = _list_attract_images()
    return render_template("admin/display.html", images=images)


@display_bp.route("/upload", methods=["POST"])
def upload():
    file = request.files.get("file")
    if not file or not file.filename:
        flash("No file selected.", "error")
        return redirect(url_for("display.index"))

    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_IMAGE_EXTS:
        flash(f"Invalid file type: {ext}. Only JPG and PNG are allowed.", "error")
        return redirect(url_for("display.index"))

    ATTRACT_DIR.mkdir(parents=True, exist_ok=True)
    dest = ATTRACT_DIR / Path(file.filename).name
    file.save(dest)
    flash(f"Attract image uploaded: {dest.name}", "success")
    return redirect(url_for("display.index"))


@display_bp.route("/delete/<filename>", methods=["POST"])
def delete(filename):
    target = ATTRACT_DIR / Path(filename).name
    if target.exists() and target.is_file():
        target.unlink()
        flash(f"Deleted: {filename}", "success")
    else:
        flash(f"File not found: {filename}", "error")
    return redirect(url_for("display.index"))


@display_bp.route("/asset/<filename>")
def asset(filename):
    path = ATTRACT_DIR / Path(filename).name
    if path.exists() and path.is_file():
        return send_file(path)
    return "Not found", 404
