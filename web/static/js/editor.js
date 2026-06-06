/**
 * oi-booth template editor
 * Pure vanilla JS canvas-based layout editor.
 */

(function () {
  'use strict';

  // ── State ────────────────────────────────────────────────────────────────
  const state = {
    name: 'New Template',
    orientation: 'portrait',
    captures: 1,
    background: '(20, 20, 20)',
    backgroundImage: '',
    overlay: '',
    margin: 20,
    footer_text1: '',
    footer_text2: '',
    text_color: '(255, 255, 255)',
    // photo zones as fractions of canvas [x, y, w, h]
    zones: [],
  };

  // ── Canvas setup ─────────────────────────────────────────────────────────
  const canvas = document.getElementById('editorCanvas');
  const ctx = canvas.getContext('2d');
  let bgImg = null;
  let overlayImg = null;

  function canvasSize() {
    if (state.orientation === 'landscape') return { w: 600, h: 400 };
    return { w: 400, h: 600 };
  }

  function resizeCanvas() {
    const { w, h } = canvasSize();
    canvas.width = w;
    canvas.height = h;
    canvas.style.maxWidth = '100%';
  }

  // ── Zone presets ─────────────────────────────────────────────────────────
  const ZONE_PRESETS = {
    portrait: {
      1: [{ x: 0.05, y: 0.05, w: 0.90, h: 0.75 }],
      2: [
        { x: 0.05, y: 0.03, w: 0.90, h: 0.44 },
        { x: 0.05, y: 0.50, w: 0.90, h: 0.44 },
      ],
      4: [
        { x: 0.04, y: 0.03, w: 0.44, h: 0.44 },
        { x: 0.52, y: 0.03, w: 0.44, h: 0.44 },
        { x: 0.04, y: 0.50, w: 0.44, h: 0.44 },
        { x: 0.52, y: 0.50, w: 0.44, h: 0.44 },
      ],
    },
    landscape: {
      1: [{ x: 0.05, y: 0.05, w: 0.90, h: 0.72 }],
      2: [
        { x: 0.03, y: 0.05, w: 0.45, h: 0.72 },
        { x: 0.52, y: 0.05, w: 0.45, h: 0.72 },
      ],
      4: [
        { x: 0.02, y: 0.04, w: 0.23, h: 0.44 },
        { x: 0.27, y: 0.04, w: 0.23, h: 0.44 },
        { x: 0.52, y: 0.04, w: 0.23, h: 0.44 },
        { x: 0.77, y: 0.04, w: 0.21, h: 0.44 },
      ],
    },
  };

  function applyZonePreset() {
    const key = Math.min(state.captures, 4);
    const presets = ZONE_PRESETS[state.orientation];
    state.zones = (presets[key] || presets[1]).map(z => ({ ...z }));
  }

  // ── Rendering ─────────────────────────────────────────────────────────────
  function parseColor(val) {
    // Accept "(R, G, B)" or "#rrggbb"
    if (!val) return '#141414';
    if (val.startsWith('#')) return val;
    const m = val.match(/(\d+)\s*,\s*(\d+)\s*,\s*(\d+)/);
    if (m) return `rgb(${m[1]},${m[2]},${m[3]})`;
    return '#141414';
  }

  function draw() {
    const { w, h } = canvasSize();
    ctx.clearRect(0, 0, w, h);

    // Background
    if (bgImg) {
      ctx.drawImage(bgImg, 0, 0, w, h);
    } else {
      ctx.fillStyle = parseColor(state.background);
      ctx.fillRect(0, 0, w, h);
    }

    // Photo zones
    state.zones.forEach((z, i) => {
      const px = z.x * w, py = z.y * h, pw = z.w * w, ph = z.h * h;
      // Fill
      ctx.fillStyle = 'rgba(255,255,255,0.07)';
      ctx.fillRect(px, py, pw, ph);
      // Border
      ctx.strokeStyle = 'rgba(249,115,22,0.7)';
      ctx.lineWidth = 2;
      ctx.setLineDash([6, 3]);
      ctx.strokeRect(px + 1, py + 1, pw - 2, ph - 2);
      ctx.setLineDash([]);
      // Label
      ctx.fillStyle = 'rgba(249,115,22,0.8)';
      ctx.font = 'bold 13px system-ui, sans-serif';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(`Photo ${i + 1}`, px + pw / 2, py + ph / 2);
    });

    // Overlay
    if (overlayImg) {
      ctx.globalAlpha = 0.85;
      ctx.drawImage(overlayImg, 0, 0, w, h);
      ctx.globalAlpha = 1;
    }

    // Footer text area (bottom strip)
    if (state.footer_text1 || state.footer_text2) {
      const footerH = 48;
      ctx.fillStyle = 'rgba(0,0,0,0.55)';
      ctx.fillRect(0, h - footerH, w, footerH);
      ctx.fillStyle = parseColor(state.text_color);
      ctx.font = 'bold 14px system-ui, sans-serif';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'top';
      ctx.fillText(state.footer_text1, w / 2, h - footerH + 4);
      ctx.font = '12px system-ui, sans-serif';
      ctx.fillStyle = 'rgba(255,255,255,0.55)';
      ctx.fillText(state.footer_text2, w / 2, h - footerH + 24);
    }
  }

  // ── Controls wiring ───────────────────────────────────────────────────────
  function bindInput(id, stateKey, transform) {
    const el = document.getElementById(id);
    if (!el) return;
    el.addEventListener('input', () => {
      state[stateKey] = transform ? transform(el.value) : el.value;
      if (stateKey === 'orientation' || stateKey === 'captures') {
        resizeCanvas();
        applyZonePreset();
      }
      if (stateKey === 'backgroundImage') loadBgImage(el.value);
      if (stateKey === 'overlay') loadOverlayImage(el.value);
      draw();
    });
  }

  bindInput('tplName',       'name');
  bindInput('tplOrientation','orientation');
  bindInput('tplCaptures',   'captures',   v => parseInt(v));
  bindInput('tplBackground', 'background');
  bindInput('tplBgImage',    'backgroundImage');
  bindInput('tplOverlay',    'overlay');
  bindInput('tplMargin',     'margin',     v => parseInt(v));
  bindInput('tplFooter1',    'footer_text1');
  bindInput('tplFooter2',    'footer_text2');
  bindInput('tplTextColor',  'text_color');

  // ── Image loading ─────────────────────────────────────────────────────────
  function loadBgImage(filename) {
    if (!filename) { bgImg = null; draw(); return; }
    const img = new Image();
    img.onload = () => { bgImg = img; draw(); };
    img.onerror = () => { bgImg = null; draw(); };
    img.src = `/admin/asset/background/${filename}`;
  }

  function loadOverlayImage(filename) {
    if (!filename) { overlayImg = null; draw(); return; }
    const img = new Image();
    img.onload = () => { overlayImg = img; draw(); };
    img.onerror = () => { overlayImg = null; draw(); };
    img.src = `/admin/asset/overlay/${filename}`;
  }

  // ── Save / Load ───────────────────────────────────────────────────────────
  window.saveTemplate = async function () {
    const { zones: _, ...payload } = { ...state }; // zones are a preview only, not saved
    const res = await fetch('/admin/templates/save', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (data.ok) {
      showToast(`Saved "${state.name}"`);
      setTimeout(() => location.reload(), 800);
    } else {
      showToast('Save failed: ' + data.error, true);
    }
  };

  window.loadTemplate = async function (filename) {
    const res = await fetch(`/admin/templates/load/${filename}`);
    const data = await res.json();
    if (!data.ok) { showToast('Load failed', true); return; }
    Object.assign(state, data);
    syncFormToState();
    resizeCanvas();
    applyZonePreset();
    if (state.backgroundImage) loadBgImage(state.backgroundImage);
    if (state.overlay) loadOverlayImage(state.overlay);
    draw();
    showToast(`Loaded "${state.name}"`);
  };

  window.deleteTemplate = async function (filename, name) {
    if (!confirm(`Delete template "${name}"?`)) return;
    await fetch(`/admin/templates/delete/${filename}`, { method: 'POST' });
    location.reload();
  };

  function syncFormToState() {
    const fields = {
      tplName: 'name', tplOrientation: 'orientation',
      tplCaptures: 'captures', tplBackground: 'background',
      tplBgImage: 'backgroundImage', tplOverlay: 'overlay',
      tplMargin: 'margin', tplFooter1: 'footer_text1',
      tplFooter2: 'footer_text2', tplTextColor: 'text_color',
    };
    Object.entries(fields).forEach(([id, key]) => {
      const el = document.getElementById(id);
      if (el) el.value = state[key] || '';
    });
  }

  // ── Toast ─────────────────────────────────────────────────────────────────
  function showToast(msg, isError = false) {
    const t = document.createElement('div');
    t.textContent = msg;
    Object.assign(t.style, {
      position: 'fixed', bottom: '2rem', left: '50%',
      transform: 'translateX(-50%)',
      background: isError ? '#dc2626' : '#16a34a',
      color: '#fff', padding: '0.6rem 1.5rem',
      borderRadius: '8px', fontSize: '0.875rem',
      fontWeight: '600', zIndex: 9999,
      boxShadow: '0 8px 24px rgba(0,0,0,0.4)',
    });
    document.body.appendChild(t);
    setTimeout(() => t.remove(), 2500);
  }

  // ── Init ──────────────────────────────────────────────────────────────────
  resizeCanvas();
  applyZonePreset();
  draw();
})();
