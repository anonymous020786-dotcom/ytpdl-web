"""Post-download audio tagging.

Ported unchanged from the desktop app's ``ytpdl/core/tagging.py``. yt-dlp
already embeds standard metadata and cover art via its post-processors; this
adds the heuristic layer on top: parse the video title into artist / song
title / genre, and set album + track number from the playlist context.
"""

from __future__ import annotations

import logging
from pathlib import Path

from mutagen import File as MutagenFile
from mutagen.easymp4 import EasyMP4
from mutagen.mp3 import EasyMP3

from .models import VideoInfo
from .titleparse import extract_genre, split_artist_title

log = logging.getLogger(__name__)

_EASY = {".mp3": EasyMP3, ".m4a": EasyMP4, ".mp4": EasyMP4}


def tag_audio_file(
    path: str | Path,
    video: VideoInfo,
    index: int,
    playlist_title: str = "",
    playlist_author: str = "",
) -> None:
    p = Path(path)
    if not p.exists():
        return

    genre, cleaned = extract_genre(video.title)
    parsed = split_artist_title(cleaned)
    song_title, artists = (parsed[0], parsed[1]) if parsed else (cleaned, [video.author])

    tags: dict[str, str] = {}
    if song_title:
        tags["title"] = song_title
    if artists:
        tags["artist"] = ", ".join(a for a in artists if a)
    if genre:
        tags["genre"] = genre
    if playlist_title:
        tags["album"] = playlist_title
    if playlist_author:
        tags["albumartist"] = playlist_author
    if index > 0:
        tags["tracknumber"] = str(index)

    try:
        opener = _EASY.get(p.suffix.lower())
        audio = opener(str(p)) if opener else MutagenFile(str(p), easy=True)
        if audio is None:
            log.debug("mutagen could not open %s", p.name)
            return
        for key, value in tags.items():
            try:
                audio[key] = value
            except (KeyError, ValueError):
                continue
        audio.save()
    except Exception as exc:  # noqa: BLE001 - tagging must never break a download
        log.warning("Tagging failed for %s: %s", p.name, exc)
