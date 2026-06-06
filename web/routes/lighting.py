"""
Lighting Controls — LED management for capture and print LEDs.
Phone-accessible at /admin/lighting.
Sends LED commands via IPC and reads current LED state from LED state file.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from flask import Blueprint, render_template, request, jsonify
from booth.ipc import send_command, read_led_state

lighting_bp = Blueprint("lighting", __name__)

VALID_LEDS = ("capture", "print", "all")
VALID_ACTIONS = ("on", "off", "blink")


@lighting_bp.route("/")
def index():
    led_state = read_led_state()
    return render_template("admin/lighting.html", led_state=led_state)


@lighting_bp.route("/command", methods=["POST"])
def command():
    data = request.get_json(silent=True) or {}
    led = data.get("led", "").strip()
    action = data.get("action", "").strip()

    if led not in VALID_LEDS:
        return jsonify({"ok": False, "error": "Invalid led"}), 400
    if action not in VALID_ACTIONS:
        return jsonify({"ok": False, "error": "Invalid action"}), 400

    send_command("set_led", led=led, state=action)
    return jsonify({"ok": True, "led": led, "action": action})


@lighting_bp.route("/api/status")
def api_status():
    return jsonify(read_led_state())
