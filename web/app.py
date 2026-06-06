"""
oi-booth web server
===================
Runs alongside pibooth on the Pi.

  /admin           — operator admin panel
  /admin/copilot   — live remote control (CoPilot)
  /admin/templates — drag-and-drop template editor
  /gallery         — guest photo retrieval
  /health          — status check
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

app = Flask(__name__)
app.secret_key = os.environ.get("OI_SECRET_KEY", "oi-booth-dev-key")

app.register_blueprint(admin_bp,     url_prefix="/admin")
app.register_blueprint(gallery_bp,   url_prefix="/gallery")
app.register_blueprint(copilot_bp,   url_prefix="/admin/copilot")
app.register_blueprint(templates_bp, url_prefix="/admin/templates")


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
