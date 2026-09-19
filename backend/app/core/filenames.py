"""Filename-template expansion and cross-platform filename sanitising.

Ported unchanged from the desktop app's ``ytpdl/core/filenames.py``.
"""

from __future__ import annotations

import re

from .models import VideoInfo
from .titleparse import extract_genre, split_artist_title

_INVALID_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED = {
    "CON", "PRN", "AUX", "NUL", "CLOCK$",
    *(f"COM{i}" for i in range(10)),
    *(f"LPT{i}" for i in range(10)),
}


def clean_filename(name: str, fallback: str = "video") -> str:
    name = _INVALID_CHARS.sub("_", name).strip().strip(".")
    name = re.sub(r"\s+", " ", name)
    if name.split(".")[0].upper() in _RESERVED:
        name = f"_{name}"
    return name[:180] or fallback


def render_template(
    template: str,
    video: VideoInfo,
    index: int,
    playlist_title: str = "",
) -> str:
    """Expand ``$token`` placeholders. ``index`` is 1-based."""
    genre, cleaned = extract_genre(video.title)
    parsed = split_artist_title(cleaned)
    song_title, artists = (parsed[0], parsed[1]) if parsed else ("", [])

    mapping = {
        "$title": cleaned,
        "$index": str(index),
        "$artist": ", ".join(artists),
        "$songtitle": song_title,
        "$channel": video.author,
        "$videoid": video.id,
        "$playlist": playlist_title,
        "$genre": genre,
    }
    result = template
    for token, value in mapping.items():
        result = result.replace(token, value)
    result = result.strip(" -")
    return clean_filename(result or cleaned or video.title)
