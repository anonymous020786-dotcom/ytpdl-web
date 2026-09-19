"""Locate an FFmpeg binary.

Ported from the desktop app's ``ytpdl/core/ffmpeg.py``, minus the PyInstaller
bundle-root lookup (irrelevant in a container). Search order: ``ffmpeg`` on
``PATH`` (install it in the image via ``apt-get install ffmpeg``), then the
binary vendored by the optional ``imageio-ffmpeg`` package.
"""

from __future__ import annotations

import functools
import logging
import shutil
import subprocess
from pathlib import Path

log = logging.getLogger(__name__)

_EXE = "ffmpeg"


@functools.lru_cache(maxsize=1)
def ffmpeg_path() -> str | None:
    on_path = shutil.which(_EXE)
    if on_path:
        return on_path

    try:
        import imageio_ffmpeg

        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if exe and Path(exe).is_file():
            return exe
    except Exception as exc:  # noqa: BLE001 - optional dependency; any failure = unavailable
        log.debug("imageio-ffmpeg unavailable: %s", exc)

    return None


def ffmpeg_dir() -> str | None:
    path = ffmpeg_path()
    return str(Path(path).parent) if path else None


def has_ffmpeg() -> bool:
    return ffmpeg_path() is not None


@functools.lru_cache(maxsize=1)
def ffmpeg_version() -> str:
    path = ffmpeg_path()
    if not path:
        return ""
    try:
        out = subprocess.run(
            [path, "-version"], capture_output=True, text=True, timeout=5, check=False,
        )
        first = out.stdout.splitlines()[0] if out.stdout else ""
        return first.replace("ffmpeg version ", "").split(" ")[0]
    except (OSError, subprocess.SubprocessError, IndexError):
        return ""


def reset_cache() -> None:
    ffmpeg_path.cache_clear()
    ffmpeg_version.cache_clear()
