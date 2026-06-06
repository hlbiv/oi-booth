"""
Printer status routes.
Handles: printer discovery, job queue, test print, job cancellation.
All printer operations use CUPS via lpstat/lp/cancel subprocess calls.
"""

import os
import re
import subprocess
import tempfile
from pathlib import Path

from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for

printer_bp = Blueprint("printer", __name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_printers():
    """Run 'lpstat -p' and return list of printer dicts."""
    printers = []
    try:
        result = subprocess.run(
            ["lpstat", "-p"],
            capture_output=True, text=True, timeout=5
        )
        for line in result.stdout.splitlines():
            # Example lines:
            #   printer Canon_TS6300 is idle.  enabled since ...
            #   printer Canon_TS6300 is now printing ...
            #   printer Canon_TS6300 disabled since ...
            m = re.match(r"^printer\s+(\S+)\s+(.*)", line)
            if not m:
                continue
            name = m.group(1)
            rest = m.group(2)
            is_idle = "is idle" in rest
            is_paused = "disabled" in rest or "paused" in rest
            is_printing = "now printing" in rest
            if is_idle:
                status = "idle"
            elif is_paused:
                status = "paused"
            elif is_printing:
                status = "printing"
            else:
                status = "unknown"
            printers.append({
                "name": name,
                "status": status,
                "is_idle": is_idle,
                "is_paused": is_paused,
            })
    except FileNotFoundError:
        # lpstat not available
        pass
    except Exception:
        pass
    return printers


def _get_jobs():
    """Run 'lpstat -o' and return list of job dicts."""
    jobs = []
    try:
        result = subprocess.run(
            ["lpstat", "-o"],
            capture_output=True, text=True, timeout=5
        )
        for line in result.stdout.splitlines():
            # Example: Canon_TS6300-42  henry  512 Thu 05 Jun 10:30
            # job-id format: <printer>-<number>
            m = re.match(r"^(\S+-\d+)\s+(\S+)\s+(\d+)\s+(.*)", line)
            if not m:
                continue
            job_id = m.group(1)
            printer_name = "-".join(job_id.split("-")[:-1])
            jobs.append({
                "job_id": job_id,
                "printer": printer_name,
                "owner": m.group(2),
                "size": m.group(3),
                "time": m.group(4).strip(),
            })
    except FileNotFoundError:
        pass
    except Exception:
        pass
    return jobs


def _get_default():
    """Run 'lpstat -d' and return default printer name, or None."""
    try:
        result = subprocess.run(
            ["lpstat", "-d"],
            capture_output=True, text=True, timeout=5
        )
        # Output: "system default destination: Canon_TS6300"
        m = re.search(r"destination:\s+(\S+)", result.stdout)
        if m:
            return m.group(1)
    except Exception:
        pass
    return None


def _make_test_image():
    """Create a small 4x6 color gradient PNG via PIL. Returns path to /tmp file."""
    from PIL import Image, ImageDraw

    width, height = 288, 432  # ~4x6 at 72 dpi
    img = Image.new("RGB", (width, height))
    draw = ImageDraw.Draw(img)

    # Draw a simple color gradient grid
    colors = [
        ("#f97316", "#ea580c"),  # orange band
        ("#3b82f6", "#1d4ed8"),  # blue band
        ("#22c55e", "#15803d"),  # green band
        ("#a855f7", "#7e22ce"),  # purple band
    ]
    band_h = height // len(colors)
    for i, (c1, c2) in enumerate(colors):
        y0 = i * band_h
        y1 = y0 + band_h
        for y in range(y0, y1):
            t = (y - y0) / max(band_h - 1, 1)
            r1, g1, b1 = int(c1[1:3], 16), int(c1[3:5], 16), int(c1[5:7], 16)
            r2, g2, b2 = int(c2[1:3], 16), int(c2[3:5], 16), int(c2[5:7], 16)
            r = int(r1 + t * (r2 - r1))
            g = int(g1 + t * (g2 - g1))
            b = int(b1 + t * (b2 - b1))
            draw.line([(0, y), (width, y)], fill=(r, g, b))

    # Label
    try:
        from PIL import ImageFont
        font = ImageFont.load_default()
        draw.text((10, 10), "oi-booth test print", fill=(255, 255, 255), font=font)
    except Exception:
        pass

    path = Path(tempfile.gettempdir()) / "oi_booth_test_print.png"
    img.save(str(path), "PNG")
    return path


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@printer_bp.route("/")
def index():
    printers = _get_printers()
    jobs = _get_jobs()
    default_printer = _get_default()
    return render_template(
        "admin/printer.html",
        printers=printers,
        jobs=jobs,
        default_printer=default_printer,
    )


@printer_bp.route("/api/status")
def api_status():
    printers = _get_printers()
    jobs = _get_jobs()
    default_printer = _get_default()
    # Attach jobs to each printer for convenience
    for p in printers:
        p["jobs"] = [j for j in jobs if j["printer"] == p["name"]]
    return jsonify({
        "printers": printers,
        "default_printer": default_printer,
        "all_jobs": jobs,
    })


@printer_bp.route("/test", methods=["POST"])
def test_print():
    printer_name = request.form.get("printer_name", "").strip()
    try:
        image_path = _make_test_image()
    except Exception as e:
        flash(f"Could not create test image: {e}", "error")
        return redirect(url_for("printer.index"))

    cmd = ["lp"]
    if printer_name:
        cmd += ["-d", printer_name]
    cmd.append(str(image_path))

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            # Extract job id from output like "request id is Canon_TS6300-42 (1 file(s))"
            m = re.search(r"request id is (\S+)", result.stdout)
            job_id = m.group(1) if m else "unknown"
            flash(f"Test print sent (job {job_id}).", "success")
        else:
            flash(f"Print failed: {result.stderr.strip() or 'unknown error'}", "error")
    except FileNotFoundError:
        flash("lp command not found — is CUPS installed?", "error")
    except Exception as e:
        flash(f"Print error: {e}", "error")

    return redirect(url_for("printer.index"))


@printer_bp.route("/cancel/<path:job_id>", methods=["POST"])
def cancel_job(job_id):
    # Sanitise job_id to only allow safe characters
    if not re.match(r"^[\w.-]+-\d+$", job_id):
        flash("Invalid job ID.", "error")
        return redirect(url_for("printer.index"))

    try:
        result = subprocess.run(
            ["cancel", job_id],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            flash(f"Job {job_id} cancelled.", "success")
        else:
            flash(f"Cancel failed: {result.stderr.strip() or 'unknown error'}", "error")
    except FileNotFoundError:
        flash("cancel command not found — is CUPS installed?", "error")
    except Exception as e:
        flash(f"Cancel error: {e}", "error")

    return redirect(url_for("printer.index"))
