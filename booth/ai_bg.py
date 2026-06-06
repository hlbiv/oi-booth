"""
AI background removal — wraps rembg.
Only activates on Raspberry Pi 4 or newer (checked at import time).
On unsupported hardware this module exports a no-op `remove_background`.
"""

import re
from pathlib import Path
from PIL import Image


def _detect_pi_version() -> int:
    """Return the Pi model number (4, 5, …) or 0 if not a Pi / unknown."""
    try:
        model = Path("/proc/device-tree/model").read_text()
        m = re.search(r"Raspberry Pi (\d+)", model)
        if m:
            return int(m.group(1))
    except Exception:
        pass
    return 0


PI_VERSION = _detect_pi_version()
AI_BG_SUPPORTED = PI_VERSION >= 4

_rembg_session = None


def _get_session():
    global _rembg_session
    if _rembg_session is None:
        from rembg import new_session
        # u2net_human_seg is optimised for people — perfect for photo booths
        _rembg_session = new_session("u2net_human_seg")
    return _rembg_session


def remove_background(image: Image.Image, background: Image.Image | None = None) -> Image.Image:
    """
    Remove the background from `image` and optionally composite `background`.
    Returns the composited PIL Image.

    On Pi 3 or non-Pi hardware this is a no-op that returns the original image.
    """
    if not AI_BG_SUPPORTED:
        return image

    try:
        from rembg import remove as rembg_remove

        session = _get_session()
        # rembg returns RGBA
        no_bg: Image.Image = rembg_remove(image, session=session)

        if background is None:
            return no_bg

        # Composite onto supplied background
        bg = background.convert("RGBA").resize(no_bg.size, Image.LANCZOS)
        bg.paste(no_bg, mask=no_bg.split()[3])
        return bg.convert("RGB")

    except Exception as e:
        print(f"[oi-booth] AI background removal failed: {e}")
        return image


def load_background(path: str) -> Image.Image | None:
    """Load a background image from disk. Returns None on failure."""
    try:
        return Image.open(path).convert("RGBA")
    except Exception:
        return None
