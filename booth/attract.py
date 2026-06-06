"""
booth/attract.py
================
Manages the attract-mode slideshow images shown on the pibooth idle screen.

Images are stored in ~/.config/pibooth/attract/ (or OI_ATTRACT_DIR env var).
The plugin cycles through them at a configurable interval while the booth is
in the "wait" state, keeping guests engaged between sessions.
"""

import os
from pathlib import Path

ATTRACT_DIR = Path(os.environ.get("OI_ATTRACT_DIR",
                    Path.home() / ".config/pibooth/attract"))

SUPPORTED_EXTS = {".jpg", ".jpeg", ".png"}


def get_attract_dir() -> Path:
    """Return the attract images directory, creating it if needed."""
    ATTRACT_DIR.mkdir(parents=True, exist_ok=True)
    return ATTRACT_DIR


def list_attract_images() -> list:
    """Return a sorted list of Path objects for all attract images."""
    d = get_attract_dir()
    images = [
        p for p in sorted(d.iterdir())
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS
    ]
    return images


def get_next_attract_image(last_index: int) -> tuple:
    """
    Return the next attract image and its index, cycling through all images.

    Parameters
    ----------
    last_index : int
        The index of the last image shown (pass 0 for the first call).

    Returns
    -------
    (Path | None, int)
        The image path and its index, or (None, 0) if no images exist.
    """
    images = list_attract_images()
    if not images:
        return None, 0
    next_index = last_index % len(images)
    return images[next_index], next_index + 1


def build_pygame_surface(image_path: Path, win_size: tuple):
    """
    Load an image and scale it to fit win_size (letterbox / pillarbox).

    Parameters
    ----------
    image_path : Path
        Absolute path to a JPEG or PNG file.
    win_size : tuple
        (width, height) of the pygame window.

    Returns
    -------
    pygame.Surface
        A surface the same size as win_size, with the image centered on a
        black background.
    """
    import pygame
    from PIL import Image as PILImage

    win_w, win_h = win_size

    # Load via Pillow for reliable EXIF-aware decoding
    pil_img = PILImage.open(image_path).convert("RGB")

    # Scale to fit inside win_size, preserving aspect ratio
    img_w, img_h = pil_img.size
    scale = min(win_w / img_w, win_h / img_h)
    new_w = int(img_w * scale)
    new_h = int(img_h * scale)
    pil_img = pil_img.resize((new_w, new_h), PILImage.LANCZOS)

    # Create a black canvas and paste the scaled image centered
    canvas = PILImage.new("RGB", (win_w, win_h), (0, 0, 0))
    paste_x = (win_w - new_w) // 2
    paste_y = (win_h - new_h) // 2
    canvas.paste(pil_img, (paste_x, paste_y))

    # Convert to pygame Surface
    surface = pygame.image.fromstring(canvas.tobytes(), canvas.size, "RGB")
    return surface.convert()
