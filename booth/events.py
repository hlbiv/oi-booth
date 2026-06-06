"""
booth/events.py
===============
Event management helpers for oi-booth.

Events are stored as individual JSON files under config/events/<event_id>.json.
The currently-active event is mirrored to /tmp/oi-booth-event.json so the
pibooth plugin can read it without touching the config directory.
"""

import json
import os
import time
import uuid
from pathlib import Path

# Base directory for event JSON files.  Kept alongside pibooth config.
EVENTS_DIR = Path(os.environ.get(
    "OI_EVENTS_DIR",
    Path(__file__).parent.parent / "config" / "events",
))

# Fast-access active-event file written to /tmp so the plugin can read it
# without I/O contention.  Same path is exposed as ipc.ACTIVE_EVENT_FILE.
ACTIVE_EVENT_FILE = Path("/tmp/oi-booth-event.json")

# Storage root for photos — mirrors OI_STORAGE_DIR used by gallery routes.
STORAGE_DIR = Path(os.environ.get(
    "OI_STORAGE_DIR",
    Path.home() / "Pictures/pibooth",
))


def _slug(name: str) -> str:
    """Convert an event name to a URL-safe slug."""
    import re
    s = name.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-") or "event"


def _event_path(event_id: str) -> Path:
    return EVENTS_DIR / f"{event_id}.json"


def _load(event_id: str) -> dict | None:
    p = _event_path(event_id)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


def _save(event: dict):
    EVENTS_DIR.mkdir(parents=True, exist_ok=True)
    _event_path(event["id"]).write_text(json.dumps(event, indent=2))


# ── Public API ────────────────────────────────────────────────────────────────

def list_events() -> list:
    """Return all events sorted newest-first."""
    EVENTS_DIR.mkdir(parents=True, exist_ok=True)
    events = []
    for p in EVENTS_DIR.glob("*.json"):
        try:
            events.append(json.loads(p.read_text()))
        except Exception:
            pass
    return sorted(events, key=lambda e: e.get("created_at", 0), reverse=True)


def get_event(event_id: str) -> dict | None:
    """Return a single event dict or None."""
    return _load(event_id)


def get_active_event() -> dict | None:
    """Return the currently-active event from /tmp, or None."""
    if not ACTIVE_EVENT_FILE.exists():
        return None
    try:
        return json.loads(ACTIVE_EVENT_FILE.read_text())
    except Exception:
        return None


def create_event(name: str, date: str, template: str = "") -> dict:
    """Create a new event, persist it, and return the event dict."""
    event_id = uuid.uuid4().hex[:12]
    event = {
        "id": event_id,
        "name": name.strip(),
        "date": date.strip(),
        "slug": _slug(name),
        "active": False,
        "template": template.strip(),
        "logo_path": "",
        "created_at": time.time(),
    }
    _save(event)
    return event


def start_event(event_id: str) -> dict | None:
    """
    Mark an event as active.

    Deactivates any previously-active event, sets the chosen event active,
    and writes it to ACTIVE_EVENT_FILE so the plugin picks it up immediately.
    Returns the activated event dict, or None if not found.
    """
    # Deactivate all first
    for ev in list_events():
        if ev.get("active"):
            ev["active"] = False
            _save(ev)

    event = _load(event_id)
    if event is None:
        return None

    event["active"] = True
    _save(event)

    try:
        ACTIVE_EVENT_FILE.write_text(json.dumps(event))
    except Exception as exc:
        print(f"[oi-booth] Could not write active event file: {exc}")

    return event


def stop_event() -> None:
    """Deactivate all events and clear the /tmp active-event file."""
    for ev in list_events():
        if ev.get("active"):
            ev["active"] = False
            _save(ev)

    try:
        if ACTIVE_EVENT_FILE.exists():
            ACTIVE_EVENT_FILE.unlink()
    except Exception:
        pass


def delete_event(event_id: str) -> None:
    """
    Delete an event.  If it was active, clears the /tmp file too.
    """
    event = _load(event_id)
    if event is None:
        return

    if event.get("active"):
        stop_event()

    p = _event_path(event_id)
    if p.exists():
        p.unlink()


def event_photo_dir(event: dict) -> Path:
    """
    Return the directory where photos for *event* should be stored.

    Path pattern: <STORAGE_DIR>/events/<event_id>/
    Created on first call.
    """
    d = STORAGE_DIR / "events" / event["id"]
    d.mkdir(parents=True, exist_ok=True)
    return d


def photo_count_for_event(event: dict) -> int:
    """Return the number of photos saved under this event's directory."""
    d = STORAGE_DIR / "events" / event["id"]
    if not d.exists():
        return 0
    count = 0
    for pattern in ("*_pibooth.jpg", "*_animated.gif", "*_boomerang.gif"):
        count += len(list(d.glob(pattern)))
    return count
