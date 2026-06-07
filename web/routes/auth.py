"""
Auth routes — PIN-based session authentication.
Protects /admin/* routes behind a 4-digit PIN stored in OI_ADMIN_PIN.
Gallery routes (/gallery/*) are intentionally left unprotected.
"""

import os
import time
from functools import wraps

from flask import (
    Blueprint, render_template, request, redirect,
    url_for, flash, session,
)

auth_bp = Blueprint("auth", __name__)

_PIN = os.environ.get("OI_ADMIN_PIN", "1234")

_MAX_ATTEMPTS = 5
_LOCKOUT_SECONDS = 300  # 5 minutes

# ip -> list of failure timestamps within the lockout window
_attempts: dict = {}


def _check_lockout(ip: str) -> tuple:
    """Return (is_locked, seconds_remaining)."""
    now = time.time()
    recent = [t for t in _attempts.get(ip, []) if now - t < _LOCKOUT_SECONDS]
    _attempts[ip] = recent
    if len(recent) >= _MAX_ATTEMPTS:
        wait = int(_LOCKOUT_SECONDS - (now - recent[0]))
        return True, max(wait, 1)
    return False, 0


def _record_failure(ip: str):
    _attempts.setdefault(ip, []).append(time.time())


def _clear_attempts(ip: str):
    _attempts.pop(ip, None)


def require_pin(f):
    """Decorator — redirects to /auth/login if the session is not authenticated."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("oi_authed"):
            session["oi_next"] = request.url
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return decorated


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    ip = request.remote_addr

    if request.method == "POST":
        locked, wait = _check_lockout(ip)
        if locked:
            flash(f"Too many incorrect attempts. Try again in {wait}s.", "error")
            return redirect(url_for("auth.login"))

        pin = request.form.get("pin", "").strip()
        if pin == _PIN:
            _clear_attempts(ip)
            session["oi_authed"] = True
            next_url = session.pop("oi_next", None)
            return redirect(next_url or url_for("admin.index"))

        _record_failure(ip)
        locked, wait = _check_lockout(ip)
        remaining = _MAX_ATTEMPTS - len(_attempts.get(ip, []))
        if locked:
            flash(f"Too many incorrect attempts. Locked out for {wait}s.", "error")
        else:
            flash(f"Incorrect PIN. {remaining} attempt{'s' if remaining != 1 else ''} remaining.", "error")
        return redirect(url_for("auth.login"))

    locked, wait = _check_lockout(ip)
    if locked:
        flash(f"Too many incorrect attempts. Try again in {wait}s.", "error")
    return render_template("auth/login.html")


@auth_bp.route("/logout")
def logout():
    session.pop("oi_authed", None)
    session.pop("oi_next", None)
    return redirect(url_for("auth.login"))
