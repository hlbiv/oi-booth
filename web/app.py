"""
oi-booth web server
===================
Runs alongside pibooth on the Pi.

  /              → redirect to /admin
  /admin         — operator admin panel        (PIN protected)
  /admin/copilot — live remote control         (PIN protected)
  /admin/templates — template editor           (PIN protected)
  /admin/printer — printer status              (PIN protected)
  /admin/events/ — event management            (PIN protected)
  /admin/ops/    — health + OTA update         (PIN protected)
  /admin/lighting — LED controls               (PIN protected)
  /admin/display  — attract slideshow upload   (PIN protected)
  /auth/         — PIN login / logout          (public)
  /gallery       — guest photo gallery         (public)
  /share/        — email sharing               (public)
  /health        — status check                (public)
"""

import os
import sys

# Ensure booth package is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from flask import Flask, redirect, url_for, jsonify

from .routes.admin import admin_bp
from .routes.gallery import gallery_bp
from .routes.copilot import copilot_bp
from .routes.templates_editor import templates_bp
from .routes.auth import auth_bp
from .routes.printer import printer_bp
from .routes.events import events_bp
from .routes.sharing import sharing_bp
from .routes.ops import ops_bp
from .routes.lighting import lighting_bp
from .routes.display_settings import display_bp

app = Flask(__name__)
app.secret_key = os.environ.get("OI_SECRET_KEY", "oi-booth-dev-key")

# ── Blueprint registration ─────────────────────────────────────────────────────
app.register_blueprint(auth_bp,      url_prefix="/auth")
app.register_blueprint(admin_bp,     url_prefix="/admin")
app.register_blueprint(gallery_bp,   url_prefix="/gallery")
app.register_blueprint(copilot_bp,   url_prefix="/admin/copilot")
app.register_blueprint(templates_bp, url_prefix="/admin/templates")
app.register_blueprint(printer_bp,   url_prefix="/admin/printer")
# events_bp uses full hardcoded paths (admin + guest gallery), no prefix
app.register_blueprint(events_bp,    url_prefix="")
app.register_blueprint(sharing_bp,   url_prefix="/share")
app.register_blueprint(ops_bp,       url_prefix="/admin/ops")
app.register_blueprint(lighting_bp,  url_prefix="/admin/lighting")
app.register_blueprint(display_bp,   url_prefix="/admin/display")


@app.before_request
def _require_pin():
    """Protect all /admin/* paths with PIN auth. Public paths are exempt."""
    from flask import request as req, session as sess, redirect as redir
    public_prefixes = ("/auth/", "/gallery", "/share/", "/health", "/static/")
    if req.path == "/" or any(req.path.startswith(p) for p in public_prefixes):
        return None
    if not sess.get("oi_authed"):
        sess["oi_next"] = req.url
        return redir(url_for("auth.login"))


@app.route("/")
def index():
    return redirect(url_for("admin.index"))


@app.route("/health")
def health():
    from booth.ipc import read_status
    status = read_status()
    return jsonify({"ok": True, "service": "oi-booth", "booth": status})


if __name__ == "__main__":
    port = int(os.environ.get("OI_PORT", 5000))
    host = os.environ.get("OI_HOST", "0.0.0.0")
    app.run(host=host, port=port, debug=False)
