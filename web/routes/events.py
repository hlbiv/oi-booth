"""
Event management routes.
Handles: list, create, start, stop, delete events + guest event gallery.

Blueprint is registered with url_prefix="" so admin routes live under
/admin/events/... and the guest gallery lives under /gallery/event/...
All paths are specified in full in the route decorators.
"""

import os
from pathlib import Path
from datetime import datetime

from flask import (
    Blueprint, render_template, request, redirect,
    url_for, flash, abort, send_file,
)

from booth.events import (
    list_events, get_event, create_event,
    start_event, stop_event, delete_event,
    event_photo_dir, photo_count_for_event,
    STORAGE_DIR,
)

events_bp = Blueprint("events", __name__)

GIF_SUFFIXES = ("_animated.gif", "_boomerang.gif")


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


def _event_photos(event_id: str) -> list:
    """Return photo meta dicts for all photos belonging to this event."""
    d = STORAGE_DIR / "events" / event_id
    if not d.exists():
        return []
    items = []
    for pattern in ("*_pibooth.jpg", "*_animated.gif", "*_boomerang.gif"):
        items.extend(d.glob(pattern))
    items.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return [_photo_meta(p) for p in items]


# ── Admin routes (all paths begin with /admin/events) ────────────────────────

@events_bp.route("/admin/events/")
def index():
    events = list_events()
    for ev in events:
        ev["_photo_count"] = photo_count_for_event(ev)
    return render_template("admin/events.html", events=events)


@events_bp.route("/admin/events/create", methods=["POST"])
def create():
    name = request.form.get("name", "").strip()
    date = request.form.get("date", "").strip()
    template = request.form.get("template", "").strip()

    if not name:
        flash("Event name is required.", "error")
        return redirect(url_for("events.index"))
    if not date:
        flash("Event date is required.", "error")
        return redirect(url_for("events.index"))

    event = create_event(name, date, template)
    flash(f'Event "{event["name"]}" created.', "success")
    return redirect(url_for("events.index"))


@events_bp.route("/admin/events/<event_id>/start", methods=["POST"])
def start(event_id):
    event = start_event(event_id)
    if event is None:
        flash("Event not found.", "error")
    else:
        flash(f'Event "{event["name"]}" is now active.', "success")
    return redirect(url_for("events.index"))


@events_bp.route("/admin/events/<event_id>/stop", methods=["POST"])
def stop(event_id):
    event = get_event(event_id)
    if event is None:
        flash("Event not found.", "error")
    else:
        stop_event()
        flash(f'Event "{event["name"]}" stopped.', "success")
    return redirect(url_for("events.index"))


@events_bp.route("/admin/events/<event_id>/delete", methods=["POST"])
def delete(event_id):
    event = get_event(event_id)
    if event is None:
        flash("Event not found.", "error")
    else:
        delete_event(event_id)
        flash(f'Event "{event["name"]}" deleted.', "success")
    return redirect(url_for("events.index"))


@events_bp.route("/admin/events/<event_id>/gallery")
def admin_gallery(event_id):
    return redirect(url_for("events.guest_gallery", event_id=event_id))


# ── Guest-facing event gallery ────────────────────────────────────────────────

@events_bp.route("/gallery/event/<event_id>", endpoint="guest_gallery")
def guest_gallery(event_id):
    event = get_event(event_id)
    if event is None:
        abort(404)
    photos = _event_photos(event_id)
    return render_template("events/gallery.html", event=event, photos=photos)


@events_bp.route("/gallery/event/<event_id>/photo/<filename>")
def event_photo(event_id, filename):
    """Serve a single event photo file."""
    safe_name = Path(filename).name  # strip any path traversal
    p = STORAGE_DIR / "events" / event_id / safe_name
    if not p.exists():
        abort(404)
    mime = "image/gif" if p.suffix == ".gif" else "image/jpeg"
    return send_file(p, mimetype=mime)
