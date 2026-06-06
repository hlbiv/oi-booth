/**
 * health.js — oi-booth health monitoring widget
 * Vanilla JS, no external dependencies.
 * Polls /admin/ops/api/health every 10 seconds and updates the DOM.
 */

(function () {
  "use strict";

  // ── Thresholds ──────────────────────────────────────────────────────────────
  var STORAGE_WARN_PCT  = 80;   // yellow
  var STORAGE_ERROR_PCT = 90;   // red
  var BOOTH_WARN_SECS   = 15;   // yellow — booth may be sleeping
  var BOOTH_ERROR_SECS  = 30;   // red — booth unresponsive

  // ── DOM helpers ─────────────────────────────────────────────────────────────
  function el(id) { return document.getElementById(id); }

  function setDot(dotEl, status) {
    // status: "ok" | "warn" | "error" | "unknown"
    dotEl.className = "health-dot health-dot--" + status;
    dotEl.title = {
      ok:      "OK",
      warn:    "Warning",
      error:   "Error",
      unknown: "Unknown",
    }[status] || status;
  }

  function setLabel(labelEl, text) {
    if (labelEl) labelEl.textContent = text;
  }

  // ── Status color logic ──────────────────────────────────────────────────────
  function storageStatus(data) {
    if (!data) return "unknown";
    var pct = data.used_pct || 0;
    if (pct >= STORAGE_ERROR_PCT) return "error";
    if (pct >= STORAGE_WARN_PCT)  return "warn";
    return "ok";
  }

  function cameraStatus(data) {
    if (!data) return "unknown";
    return data.ok ? "ok" : "error";
  }

  function printerStatus(data) {
    if (!data) return "unknown";
    // Printer is optional — missing is a warning, not an error
    return data.ok ? "ok" : "warn";
  }

  function boothStatus(data) {
    if (!data) return "unknown";
    var secs = data.last_seen_seconds_ago;
    if (secs === null || secs === undefined) return "error";
    if (secs >= BOOTH_ERROR_SECS) return "error";
    if (secs >= BOOTH_WARN_SECS)  return "warn";
    return "ok";
  }

  // ── Nav dot (global indicator in base.html) ─────────────────────────────────
  function updateNavDot(overallOk) {
    var navDot = el("nav-health-dot");
    if (!navDot) return;
    navDot.className = "nav-health-dot " + (overallOk ? "nav-health-dot--ok" : "nav-health-dot--error");
    navDot.title = overallOk ? "All systems OK" : "System issue detected";
  }

  // ── Main widget update ──────────────────────────────────────────────────────
  function updateHealthWidget(data) {
    if (!data) return;

    // Storage
    var storageDot   = el("dot-storage");
    var storageLabel = el("label-storage");
    if (storageDot) setDot(storageDot, storageStatus(data.storage));
    if (storageLabel && data.storage) {
      storageLabel.textContent =
        data.storage.used_pct + "% used — " +
        data.storage.free_gb + " GB free";
    }

    // Camera
    var cameraDot   = el("dot-camera");
    var cameraLabel = el("label-camera");
    if (cameraDot) setDot(cameraDot, cameraStatus(data.camera));
    if (cameraLabel && data.camera) {
      cameraLabel.textContent = data.camera.detected ? "Detected" : "Not detected";
    }

    // Printer
    var printerDot   = el("dot-printer");
    var printerLabel = el("label-printer");
    if (printerDot) setDot(printerDot, printerStatus(data.printer));
    if (printerLabel && data.printer) {
      printerLabel.textContent = data.printer.printer_name || "No default printer";
    }

    // Booth
    var boothDot   = el("dot-booth");
    var boothLabel = el("label-booth");
    if (boothDot) setDot(boothDot, boothStatus(data.booth_state));
    if (boothLabel && data.booth_state) {
      var secs = data.booth_state.last_seen_seconds_ago;
      var state = data.booth_state.state || "unknown";
      boothLabel.textContent = secs !== null && secs !== undefined
        ? state + " — " + secs + "s ago"
        : state;
    }

    // Last photo
    var lastPhotoEl = el("last-photo-info");
    if (lastPhotoEl && data.last_photo) {
      var count = data.last_photo.photo_count || 0;
      var sid   = data.last_photo.session_id || "—";
      lastPhotoEl.textContent = count + " photos · last session: " + sid;
    }

    // Overall nav dot
    updateNavDot(data.ok);

    // Timestamp
    var tsEl = el("health-last-updated");
    if (tsEl) {
      tsEl.textContent = "Updated " + new Date().toLocaleTimeString();
    }
  }

  // ── Polling ─────────────────────────────────────────────────────────────────
  function poll() {
    fetch("/admin/ops/api/health")
      .then(function (r) { return r.json(); })
      .then(function (data) { updateHealthWidget(data); })
      .catch(function () {
        // On fetch failure mark booth as error
        updateNavDot(false);
      });
  }

  // Kick off immediately, then every 10 s
  document.addEventListener("DOMContentLoaded", function () {
    poll();
    setInterval(poll, 10000);
  });

  // Expose for inline use if needed
  window.updateHealthWidget = updateHealthWidget;
}());
