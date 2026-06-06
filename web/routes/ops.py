"""
Ops routes — health monitoring and over-the-air update.
Handles: system health checks, git-based update flow.
"""

import os
import shutil
import subprocess
import time
from pathlib import Path

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify

ops_bp = Blueprint("ops", __name__)

STORAGE_DIR = Path(os.environ.get("OI_STORAGE_DIR", Path.home() / "Pictures/pibooth"))
REPO_DIR = Path(os.environ.get("OI_REPO_DIR", Path(__file__).resolve().parents[2]))

# Token required in POST body to confirm destructive update action
UPDATE_CONFIRM_TOKEN = "i-understand-this-will-restart"


# ── Health check helpers ──────────────────────────────────────────────────────

def _check_storage() -> dict:
    """Disk usage for OI_STORAGE_DIR (or its mount point)."""
    target = STORAGE_DIR
    # Fall back to root mount if storage dir doesn't exist yet
    check_path = target if target.exists() else Path("/")
    try:
        total, used, free = shutil.disk_usage(check_path)
        used_pct = round(used / total * 100) if total else 0
        free_gb = round(free / 1e9, 2)
        return {
            "ok": used_pct < 90,
            "free_gb": free_gb,
            "used_pct": used_pct,
            "path": str(target),
        }
    except Exception as exc:
        return {"ok": False, "free_gb": 0, "used_pct": 0, "error": str(exc)}


def _check_camera() -> dict:
    """Detect camera via vcgencmd (Pi) or /dev/video* fallback."""
    # Pi-native check
    try:
        result = subprocess.run(
            ["vcgencmd", "get_camera"],
            capture_output=True, text=True, timeout=3
        )
        detected = "detected=1" in result.stdout
        return {"ok": detected, "detected": detected, "method": "vcgencmd"}
    except FileNotFoundError:
        pass
    except Exception:
        pass

    # Generic V4L2 device fallback
    video_devs = list(Path("/dev").glob("video*"))
    detected = len(video_devs) > 0
    return {"ok": detected, "detected": detected, "method": "v4l2",
            "devices": [str(d) for d in video_devs]}


def _check_printer() -> dict:
    """Check default CUPS printer via lpstat."""
    try:
        result = subprocess.run(
            ["lpstat", "-d"],
            capture_output=True, text=True, timeout=5
        )
        output = result.stdout.strip()
        # "system default destination: <name>"
        if ":" in output and result.returncode == 0:
            printer_name = output.split(":", 1)[1].strip()
            ok = bool(printer_name) and printer_name != "no system default destination"
            return {"ok": ok, "printer_name": printer_name if ok else None}
        return {"ok": False, "printer_name": None}
    except FileNotFoundError:
        return {"ok": False, "printer_name": None, "error": "lpstat not found"}
    except Exception as exc:
        return {"ok": False, "printer_name": None, "error": str(exc)}


def _check_booth() -> dict:
    """Read IPC status file and report recency."""
    from booth.ipc import read_status, STATUS_FILE
    status = read_status()
    ts = status.get("ts", 0)
    state = status.get("state", "unknown")
    last_seen = round(time.time() - ts) if ts else None

    # Consider booth OK if status file written within 30 s
    ok = bool(ts) and last_seen is not None and last_seen < 30
    return {
        "ok": ok,
        "state": state,
        "last_seen_seconds_ago": last_seen,
        "status_file_exists": STATUS_FILE.exists(),
    }


def _git_info() -> dict:
    """Return current git commit hash and timestamp."""
    try:
        commit = subprocess.run(
            ["git", "-C", str(REPO_DIR), "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5
        ).stdout.strip()
        commit_date = subprocess.run(
            ["git", "-C", str(REPO_DIR), "log", "-1", "--format=%ci"],
            capture_output=True, text=True, timeout=5
        ).stdout.strip()
        return {"commit": commit, "date": commit_date}
    except Exception:
        return {"commit": "unknown", "date": "unknown"}


def _do_update() -> dict:
    """
    Non-blocking: git pull, pip install -r requirements.txt,
    then restart both systemd services.
    Runs as a fire-and-forget Popen so the HTTP response returns immediately.
    """
    req_txt = REPO_DIR / "requirements.txt"
    script = (
        f"cd {REPO_DIR} && "
        f"git pull --ff-only && "
        f"pip install -r {req_txt} --quiet && "
        f"sudo systemctl restart oi-booth oi-web"
    )
    try:
        subprocess.Popen(
            ["bash", "-c", script],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
        )
        return {"started": True}
    except Exception as exc:
        return {"started": False, "error": str(exc)}


# ── Routes ────────────────────────────────────────────────────────────────────

@ops_bp.route("/")
def index():
    git = _git_info()
    return render_template("admin/health.html", git=git)


@ops_bp.route("/api/health")
def api_health():
    storage = _check_storage()
    camera = _check_camera()
    printer = _check_printer()
    booth = _check_booth()

    from booth.ipc import read_status
    status = read_status()

    all_ok = all([storage["ok"], camera["ok"], booth["ok"]])
    # Printer is optional — warning only, not a hard failure
    return jsonify({
        "ok": all_ok,
        "storage": storage,
        "camera": camera,
        "printer": printer,
        "booth_state": booth,
        "last_photo": {
            "session_id": status.get("last_session_id", ""),
            "photo_count": status.get("photo_count", 0),
        },
    })


@ops_bp.route("/update", methods=["POST"])
def do_update():
    token = request.form.get("confirm_token", "").strip()
    if token != UPDATE_CONFIRM_TOKEN:
        flash("Update cancelled — confirmation token missing or wrong.", "error")
        return redirect(url_for("ops.index"))

    result = _do_update()
    if result.get("started"):
        flash(
            "Update started in the background. The booth and web server will "
            "restart in ~30 seconds.",
            "success",
        )
    else:
        flash(f"Update failed to start: {result.get('error', 'unknown error')}", "error")
    return redirect(url_for("ops.index"))
