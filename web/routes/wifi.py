"""
WiFi management routes.
Uses nmcli (NetworkManager CLI) — standard on Pi OS Bullseye+.
All subprocess calls use list args to prevent injection.
"""

import re
import subprocess

from flask import Blueprint, render_template, request, jsonify

wifi_bp = Blueprint("wifi", __name__)


def _nmcli(*args, timeout=10):
    return subprocess.run(
        ["nmcli"] + list(args),
        capture_output=True, text=True, timeout=timeout
    )


def _get_status() -> dict:
    """Return current WiFi connection info."""
    try:
        r = _nmcli("-t", "-f", "DEVICE,TYPE,STATE,CONNECTION", "dev")
        for line in r.stdout.splitlines():
            parts = line.split(":")
            if len(parts) >= 4 and parts[1] == "wifi" and parts[2] == "connected":
                device = parts[0]
                ssid = ":".join(parts[3:])  # SSID may contain colons
                # get IP
                ip_r = _nmcli("-t", "-f", "IP4.ADDRESS", "dev", "show", device)
                ip = ""
                for ip_line in ip_r.stdout.splitlines():
                    if ip_line.startswith("IP4.ADDRESS"):
                        ip = ip_line.split(":", 1)[1].split("/")[0]
                        break
                return {"connected": True, "ssid": ssid, "ip": ip, "device": device}
        return {"connected": False}
    except FileNotFoundError:
        return {"connected": False, "error": "nmcli not available — install NetworkManager"}
    except Exception as e:
        return {"connected": False, "error": str(e)}


def _scan() -> list:
    """Return sorted list of visible networks. Takes ~10s with --rescan yes."""
    try:
        r = _nmcli("--mode", "multiline", "-f", "IN-USE,SSID,SIGNAL,SECURITY",
                   "dev", "wifi", "list", "--rescan", "yes", timeout=25)
        networks, current = [], {}
        for line in r.stdout.splitlines() + [""]:
            if not line.strip():
                ssid = current.get("ssid", "").strip()
                if ssid:
                    networks.append({
                        "ssid": ssid,
                        "signal": _safe_int(current.get("signal", "0")),
                        "security": current.get("security", "").strip(),
                        "in_use": current.get("in_use", "").strip() == "*",
                    })
                current = {}
                continue
            m = re.match(r"^([A-Z0-9_-]+)(?:\[\d+\])?\s*:\s*(.*)", line.strip())
            if m:
                key, val = m.group(1), m.group(2)
                current[key.lower().replace("-", "_")] = val

        # de-dup by SSID, keep strongest signal
        seen: dict = {}
        for n in networks:
            if n["ssid"] not in seen or n["signal"] > seen[n["ssid"]]["signal"]:
                seen[n["ssid"]] = n
        return sorted(seen.values(), key=lambda n: (-n["in_use"], -n["signal"]))
    except FileNotFoundError:
        return []
    except Exception:
        return []


def _safe_int(val: str) -> int:
    try:
        return int(val.strip())
    except Exception:
        return 0


@wifi_bp.route("/")
def index():
    return render_template("admin/wifi.html", status=_get_status())


@wifi_bp.route("/api/status")
def api_status():
    return jsonify(_get_status())


@wifi_bp.route("/api/scan")
def api_scan():
    return jsonify({"networks": _scan()})


@wifi_bp.route("/api/connect", methods=["POST"])
def api_connect():
    data = request.get_json(force=True) or {}
    ssid = data.get("ssid", "").strip()
    password = data.get("password", "").strip()

    if not ssid:
        return jsonify({"ok": False, "error": "SSID required"}), 400

    cmd = ["nmcli", "dev", "wifi", "connect", ssid]
    if password:
        cmd += ["password", password]

    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=35)
        if r.returncode == 0:
            return jsonify({"ok": True})
        err = r.stderr.strip() or r.stdout.strip() or "Connection failed"
        return jsonify({"ok": False, "error": err})
    except FileNotFoundError:
        return jsonify({"ok": False, "error": "nmcli not available"}), 503
    except subprocess.TimeoutExpired:
        return jsonify({"ok": False, "error": "Connection timed out"}), 504
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@wifi_bp.route("/api/forget", methods=["POST"])
def api_forget():
    data = request.get_json(force=True) or {}
    ssid = data.get("ssid", "").strip()
    if not ssid:
        return jsonify({"ok": False, "error": "SSID required"}), 400
    try:
        r = _nmcli("con", "delete", ssid, timeout=10)
        if r.returncode == 0:
            return jsonify({"ok": True})
        return jsonify({"ok": False, "error": r.stderr.strip() or "Failed"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
