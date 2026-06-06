"""
CoPilot — remote operator control page.
Phone-accessible at /admin/copilot.
Reads live status from the plugin and sends commands via IPC files.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from flask import Blueprint, render_template, request, redirect, url_for, jsonify
from booth.ipc import send_command, read_status

copilot_bp = Blueprint("copilot", __name__)

VALID_MODES = ("photo", "gif", "boomerang")
VALID_ACTIONS = ("capture", "restart", "set_mode")


@copilot_bp.route("/")
def index():
    status = read_status()
    return render_template("admin/copilot.html", status=status)


@copilot_bp.route("/command", methods=["POST"])
def command():
    action = request.form.get("action", "").strip()
    if action not in VALID_ACTIONS:
        return jsonify({"ok": False, "error": "Invalid action"}), 400

    kwargs = {}
    if action == "set_mode":
        mode = request.form.get("mode", "photo").strip()
        if mode not in VALID_MODES:
            return jsonify({"ok": False, "error": "Invalid mode"}), 400
        kwargs["mode"] = mode

    send_command(action, **kwargs)
    return jsonify({"ok": True, "action": action})


@copilot_bp.route("/status")
def status():
    return jsonify(read_status())
