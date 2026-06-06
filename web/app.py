"""
oi-booth web server
===================
Runs alongside pibooth on the Pi. Serves:
  /admin      — operator/admin panel (config, backgrounds, maintenance)
  /gallery/<session_id>  — user photo retrieval page
  /health     — status check
"""

import os
import json
import subprocess
from pathlib import Path
from flask import Flask, render_template, request, redirect, url_for, send_file, jsonify, flash

from .routes.admin import admin_bp
from .routes.gallery import gallery_bp

app = Flask(__name__)
app.secret_key = os.environ.get("OI_SECRET_KEY", "oi-booth-dev-key")

app.register_blueprint(admin_bp, url_prefix="/admin")
app.register_blueprint(gallery_bp, url_prefix="/gallery")


@app.route("/")
def index():
    return redirect(url_for("admin.index"))


@app.route("/health")
def health():
    return jsonify({"ok": True, "service": "oi-booth"})


if __name__ == "__main__":
    port = int(os.environ.get("OI_PORT", 5000))
    host = os.environ.get("OI_HOST", "0.0.0.0")
    app.run(host=host, port=port, debug=False)
