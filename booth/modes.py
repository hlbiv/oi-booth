"""
GIF and Boomerang mode processing.
Takes a list of PIL Image captures and returns the output file path.
"""

import os
import tempfile
from pathlib import Path
from PIL import Image


def make_gif(captures: list, output_path: str, fps: int = 8,
             max_size: tuple = (800, 600)) -> str:
    """
    Stitch a list of PIL Images into an animated GIF.
    Returns the output path.
    """
    if not captures:
        raise ValueError("No captures provided")

    frames = []
    for img in captures:
        frame = img.copy().convert("RGB")
        frame.thumbnail(max_size, Image.LANCZOS)
        frames.append(frame)

    duration_ms = int(1000 / fps)
    frames[0].save(
        output_path,
        format="GIF",
        save_all=True,
        append_images=frames[1:],
        loop=0,
        duration=duration_ms,
        optimize=False,
    )
    return output_path


def make_boomerang(captures: list, output_path: str, fps: int = 10,
                   max_size: tuple = (800, 600)) -> str:
    """
    Stitch captures into a boomerang GIF (forward + reverse, looping).
    Returns the output path.
    """
    if not captures:
        raise ValueError("No captures provided")

    frames = []
    for img in captures:
        frame = img.copy().convert("RGB")
        frame.thumbnail(max_size, Image.LANCZOS)
        frames.append(frame)

    # Forward + reverse (skip duplicating first/last frame)
    boomerang = frames + frames[-2:0:-1]

    duration_ms = int(1000 / fps)
    boomerang[0].save(
        output_path,
        format="GIF",
        save_all=True,
        append_images=boomerang[1:],
        loop=0,
        duration=duration_ms,
        optimize=False,
    )
    return output_path


def output_path_for(base_jpg_path: str, mode: str) -> str:
    """Derive the GIF output path from the base JPEG path."""
    p = Path(base_jpg_path)
    suffix = "_boomerang.gif" if mode == "boomerang" else "_animated.gif"
    return str(p.parent / (p.stem.replace("_pibooth", "") + suffix))
