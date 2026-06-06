"""
Email sharing routes.
Allows guests to receive their photo by email after a booth session.
"""

import os
from pathlib import Path

from flask import Blueprint, request, jsonify, render_template

sharing_bp = Blueprint("sharing", __name__)

STORAGE_DIR = Path(os.environ.get("OI_STORAGE_DIR",
                    Path.home() / "Pictures/pibooth"))

# Fallback search path when OI_STORAGE_DIR is not set
_FALLBACK_DIRS = [
    Path.home() / "Pictures/pibooth",
    Path("/tmp/pibooth"),
]


def _find_photo(session_id: str) -> Path | None:
    """Search configured storage dir and fallbacks for a session photo."""
    search_dirs = [STORAGE_DIR] + [d for d in _FALLBACK_DIRS if d != STORAGE_DIR]
    for directory in search_dirs:
        if not directory.exists():
            continue
        for suffix in ("_pibooth.jpg", "_animated.gif", "_boomerang.gif", ".jpg", ".gif"):
            p = directory / f"{session_id}{suffix}"
            if p.exists():
                return p
        matches = list(directory.glob(f"{session_id}*"))
        if matches:
            return matches[0]
    return None


def _get_mail():
    """
    Return a configured Flask-Mail instance, or None with an error string.
    Returns (mail, error_str).
    """
    server = os.environ.get("OI_MAIL_SERVER", "").strip()
    username = os.environ.get("OI_MAIL_USERNAME", "").strip()
    password = os.environ.get("OI_MAIL_PASSWORD", "").strip()
    mail_from = os.environ.get("OI_MAIL_FROM", username).strip()
    port = int(os.environ.get("OI_MAIL_PORT", 587))

    if not server:
        return None, "Email not configured — set OI_MAIL_SERVER in your .env"
    if not username or not password:
        return None, "Email not configured — set OI_MAIL_USERNAME and OI_MAIL_PASSWORD in your .env"

    try:
        from flask_mail import Mail
        from flask import current_app

        # Apply mail config to app if not already applied
        app = current_app._get_current_object()
        app.config.setdefault("MAIL_SERVER", server)
        app.config.setdefault("MAIL_PORT", port)
        app.config.setdefault("MAIL_USERNAME", username)
        app.config.setdefault("MAIL_PASSWORD", password)
        app.config.setdefault("MAIL_DEFAULT_SENDER", mail_from)
        app.config.setdefault("MAIL_USE_TLS", port == 587)
        app.config.setdefault("MAIL_USE_SSL", port == 465)

        mail = Mail(app)
        return mail, None
    except ImportError:
        return None, "flask-mail is not installed — run: pip install flask-mail"


@sharing_bp.route("/email", methods=["POST"])
def send_email():
    """
    POST /share/email
    Body JSON: {session_id, email}
    Returns: {ok: true} or {ok: false, error: "..."}
    """
    data = request.get_json(silent=True) or {}
    session_id = (data.get("session_id") or "").strip()
    email = (data.get("email") or "").strip()

    if not session_id:
        return jsonify({"ok": False, "error": "session_id is required"}), 400
    if not email or "@" not in email:
        return jsonify({"ok": False, "error": "A valid email address is required"}), 400

    # Locate the photo file
    photo = _find_photo(session_id)
    if not photo:
        return jsonify({"ok": False, "error": "Photo not found for this session"}), 404

    # Resolve mail instance
    mail, err = _get_mail()
    if err:
        return jsonify({"ok": False, "error": err}), 503

    try:
        from flask_mail import Message

        mail_from = os.environ.get("OI_MAIL_FROM",
                    os.environ.get("OI_MAIL_USERNAME", "noreply@oi-booth.local"))
        msg = Message(
            subject="Your oi-booth photo",
            sender=mail_from,
            recipients=[email],
            body=(
                "Hey there!\n\n"
                "Your photo from the oi-booth is attached.\n\n"
                "Hope you had a great time!\n"
                "— oi-booth"
            ),
        )
        with open(photo, "rb") as f:
            mime = "image/gif" if photo.suffix == ".gif" else "image/jpeg"
            msg.attach(photo.name, mime, f.read())

        mail.send(msg)
        return jsonify({"ok": True})

    except Exception as exc:
        return jsonify({"ok": False, "error": f"Failed to send email: {exc}"}), 500


@sharing_bp.route("/email/<session_id>", methods=["GET"])
def email_form(session_id):
    """
    GET /share/email/<session_id>
    Renders a simple email capture form for guests whose browser
    doesn't support the Web Share API.
    """
    photo = _find_photo(session_id)
    if not photo:
        return render_template("share/email_form.html",
                               session_id=session_id,
                               error="Photo not found — the session ID may be incorrect."), 404

    return render_template("share/email_form.html",
                           session_id=session_id,
                           error=None)


@sharing_bp.route("/email/<session_id>", methods=["POST"])
def email_form_submit(session_id):
    """
    POST /share/email/<session_id>  (HTML form fallback)
    """
    email = (request.form.get("email") or "").strip()
    if not email or "@" not in email:
        return render_template("share/email_form.html",
                               session_id=session_id,
                               error="Please enter a valid email address."), 400

    photo = _find_photo(session_id)
    if not photo:
        return render_template("share/email_form.html",
                               session_id=session_id,
                               error="Photo not found for this session."), 404

    mail, err = _get_mail()
    if err:
        return render_template("share/email_form.html",
                               session_id=session_id,
                               error=err), 503

    try:
        from flask_mail import Message

        mail_from = os.environ.get("OI_MAIL_FROM",
                    os.environ.get("OI_MAIL_USERNAME", "noreply@oi-booth.local"))
        msg = Message(
            subject="Your oi-booth photo",
            sender=mail_from,
            recipients=[email],
            body=(
                "Hey there!\n\n"
                "Your photo from the oi-booth is attached.\n\n"
                "Hope you had a great time!\n"
                "— oi-booth"
            ),
        )
        with open(photo, "rb") as f:
            mime = "image/gif" if photo.suffix == ".gif" else "image/jpeg"
            msg.attach(photo.name, mime, f.read())

        mail.send(msg)
        return render_template("share/email_sent.html", email=email, session_id=session_id)

    except Exception as exc:
        return render_template("share/email_form.html",
                               session_id=session_id,
                               error=f"Failed to send email: {exc}"), 500
