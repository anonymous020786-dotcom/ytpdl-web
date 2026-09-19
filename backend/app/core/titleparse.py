"""Heuristic parsing of YouTube video titles into song metadata.

Ported unchanged from the desktop app (``shaked6540/YoutubePlaylistDownloader``
-> ``yt-playlist-downloader-py``): ``[Genre]`` prefix/suffix extraction with a
blocklist of promo words, and ``Artist - Title`` splitting honouring a set of
featured-artist separators.
"""

from __future__ import annotations

import re

IGNORED_GENRES = (
    "download",
    "out now",
    "monstercat",
    "mostercat",
    "video",
    "lyric",
    "release",
    "ncs",
    "records",
)
ARTIST_SEPARATORS = re.compile(
    r"\s*(?:&|,| feat\.?[ .]| ft\.?[ .]| featuring | x | vs\.? | with )\s*",
    re.IGNORECASE,
)
TITLE_SEPARATORS = (" - ", " — ", " – ")
_BRACKET_RE = re.compile(r"[\[\]【】]")


def extract_genre(title: str) -> tuple[str, str]:
    """Return ``(genre, cleaned_title)``.

    ``genre`` is the text inside the first ``[...]`` group unless it matches the
    promo blocklist; the bracketed chunks are stripped from the title either way.
    """
    normalized = title.replace("—", "-")
    parts = _BRACKET_RE.split(normalized)
    genre = parts[1].strip() if len(parts) > 1 else ""

    if genre and len(genre) >= len(normalized):
        genre = ""

    cleaned = normalized
    if genre:
        cleaned = cleaned.replace(f"[{genre}]", "").replace(f"【{genre}】", "")
        inner = _BRACKET_RE.split(cleaned)
        if len(inner) > 1 and inner[1].strip():
            cleaned = cleaned.replace(f"[{inner[1]}]", "").replace(f"【{inner[1]}】", "")

    cleaned = cleaned.strip(" -[]【】").strip()

    if any(bad in genre.lower() for bad in IGNORED_GENRES):
        genre = ""

    return genre, cleaned or normalized.strip()


def split_artist_title(title: str) -> tuple[str, list[str]] | None:
    """``"A & B - Song"`` -> ``("Song", ["A", "B"])`` or ``None`` if no dash."""
    idx = title.rfind("-")
    if idx <= 0:
        return None

    song_title = title[idx + 1 :].strip(" -")
    if not song_title:
        first = title.find("-")
        if first > 0:
            song_title = title[first + 1 :].strip(" -")
            idx = first
    if not song_title:
        return None

    artist_part = title[:idx].strip()
    performers = [a.strip() for a in ARTIST_SEPARATORS.split(artist_part) if a.strip()]
    return song_title, performers or [artist_part]
