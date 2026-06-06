"""
Auth routes — PIN-based session authentication.
Protects /admin/* routes behind a 4-digit PIN stored in OI_ADMIN_PIN.
Gallery routes (/gallery/*) are intentionally left unprotected.
"""

import os
from functools import wraps

from flask import (
    Blueprint, render_template, request, redirect,
    url_for, flash, session,
)

auth_bp = Blueprint("auth", __name__)

_PIN = os.environ.get("OI_ADMIN_PIN", "1234")


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
    if request.method == "POST":
        pin = request.form.get("pin", "").strip()
        if pin == _PIN:
            session["oi_authed"] = True
            next_url = session.pop("oi_next", None)
            return redirect(next_url or url_for("admin.index"))
        flash("Incorrect PIN. Try again.", "error")
        return redirect(url_for("auth.login"))

    return render_template("auth/login.html")


@auth_bp.route("/logout")
def logout():
    session.pop("oi_authed", None)
    session.pop("oi_next", None)
    return redirect(url_for("auth.login"))
