"""
Inter-process communication between the Flask web server and the pibooth plugin.
Uses a pair of JSON files in /tmp so no sockets or threads are needed.

Command file  (/tmp/oi-booth-cmd.json)   — web server writes, plugin reads + clears
Status file   (/tmp/oi-booth-status.json) — plugin writes, web server reads
"""

import json
import os
import time
from pathlib import Path

CMD_FILE         = Path(os.environ.get("OI_CMD_FILE",         "/tmp/oi-booth-cmd.json"))
STATUS_FILE      = Path(os.environ.get("OI_STATUS_FILE",      "/tmp/oi-booth-status.json"))
LED_STATE_FILE   = Path(os.environ.get("OI_LED_STATE_FILE",   "/tmp/oi-booth-leds.json"))
ACTIVE_EVENT_FILE = Path(os.environ.get("OI_ACTIVE_EVENT",   "/tmp/oi-booth-event.json"))

# ── Commands (web → plugin) ───────────────────────────────────────────────────

def send_command(action: str, **kwargs):
    """Write a command for the plugin to pick up."""
    payload = {"action": action, "ts": time.time(), **kwargs}
    CMD_FILE.write_text(json.dumps(payload))


def read_command() -> dict | None:
    """Read and clear the pending command. Returns None if none."""
    if not CMD_FILE.exists():
        return None
    try:
        data = json.loads(CMD_FILE.read_text())
        CMD_FILE.unlink()
        return data
    except Exception:
        try:
            CMD_FILE.unlink()
        except Exception:
            pass
        return None


# ── Status (plugin → web) ─────────────────────────────────────────────────────

def write_status(state: str, mode: str = "photo", photo_count: int = 0,
                 last_session_id: str = "", **extra):
    payload = {
        "state": state,
        "mode": mode,
        "photo_count": photo_count,
        "last_session_id": last_session_id,
        "ts": time.time(),
        **extra,
    }
    try:
        STATUS_FILE.write_text(json.dumps(payload))
    except Exception:
        pass


def read_status() -> dict:
    try:
        if STATUS_FILE.exists():
            return json.loads(STATUS_FILE.read_text())
    except Exception:
        pass
    return {"state": "unknown", "mode": "photo", "photo_count": 0,
            "last_session_id": "", "ts": 0}


# ── LED state (plugin → web) ──────────────────────────────────────────────────

def write_led_state(capture: str = "off", print_led: str = "off"):
    payload = {"capture": capture, "print": print_led, "ts": time.time()}
    try:
        LED_STATE_FILE.write_text(json.dumps(payload))
    except Exception:
        pass


def read_led_state() -> dict:
    try:
        if LED_STATE_FILE.exists():
            return json.loads(LED_STATE_FILE.read_text())
    except Exception:
        pass
    return {"capture": "off", "print": "off", "ts": 0}
