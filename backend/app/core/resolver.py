"""Turn a user-supplied string into a :class:`ResolvedSource`.

Ported unchanged from the desktop app's ``ytpdl/core/resolver.py`` — no Qt
dependency there to begin with. Uses yt-dlp in *metadata only* mode
(``extract_flat`` for collections) so even multi-thousand-video channels
resolve in a couple of seconds without touching the network more than
necessary.
"""

from __future__ import annotations

import logging
import re
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from yt_dlp import YoutubeDL

from .models import ResolvedSource, SourceKind, VideoInfo

log = logging.getLogger(__name__)

_YT_HOST = re.compile(r"(?:^|\.)(?:youtube\.com|youtu\.be|youtube-nocookie\.com)$", re.IGNORECASE)
_VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
# A bare channel URL (no tab segment) resolves, via extract_flat, to that
# channel's tab *shortcuts* (Home/Videos/Shorts/...) rather than videos — each
# entry comes back with id=<channel_id>, not a real video id. Landing
# directly on the "videos" tab avoids that; anything with an explicit tab
# (/videos, /streams, /playlists, a bare /playlist?list=...) is left alone.
_BARE_CHANNEL = re.compile(
    r"^(https?://)?(www\.)?youtube\.com/(?:@[^/?#]+|channel/[^/?#]+|c/[^/?#]+|user/[^/?#]+)/?$",
    re.IGNORECASE,
)
# YouTube adds list= (and index=/start_radio=) to the address bar just from
# watching a video *inside* a playlist or "up next" queue — not because the
# viewer asked for the playlist. Copying that URL is the single most common
# way people share/paste "this one video" links, but yt-dlp's default (with
# noplaylist=False, needed elsewhere for actual playlist links) treats a URL
# carrying both v= and list= as "download the whole playlist". Stripping the
# playlist-context params whenever a specific video is already identified
# (v= present, or a youtu.be short link) makes a pasted video link resolve to
# that video, not whatever queue it happened to be playing in. A bare
# playlist URL (.../playlist?list=..., no v=) is untouched.
_PLAYLIST_CONTEXT_PARAMS = ("list", "index", "start_radio")


class ResolveError(RuntimeError):
    pass


def looks_like_youtube(text: str) -> bool:
    text = text.strip()
    if not text:
        return False
    if _VIDEO_ID.match(text):
        return True
    from urllib.parse import urlparse

    parsed = urlparse(text if "//" in text else f"https://{text}")
    return bool(parsed.netloc and _YT_HOST.search(parsed.netloc))


def _mk_video(entry: dict) -> VideoInfo:
    vid = entry.get("id") or ""
    return VideoInfo(
        id=vid,
        title=entry.get("title") or entry.get("fulltitle") or vid or "Untitled",
        url=entry.get("webpage_url") or entry.get("url") or f"https://www.youtube.com/watch?v={vid}",
        author=entry.get("uploader") or entry.get("channel") or entry.get("playlist_uploader") or "",
        duration=entry.get("duration"),
        thumbnail=_best_thumb(entry),
    )


def _best_thumb(entry: dict) -> str:
    if entry.get("thumbnail"):
        return entry["thumbnail"]
    thumbs = entry.get("thumbnails") or []
    if thumbs:
        return thumbs[-1].get("url", "")
    vid = entry.get("id")
    return f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg" if vid else ""


def _strip_playlist_context(text: str) -> str:
    parsed = urlparse(text if "//" in text else f"https://{text}")
    if not parsed.netloc or not _YT_HOST.search(parsed.netloc):
        return text
    query = parse_qs(parsed.query)
    has_specific_video = "v" in query or parsed.netloc.lower().endswith("youtu.be")
    if not has_specific_video or "list" not in query:
        return text
    for param in _PLAYLIST_CONTEXT_PARAMS:
        query.pop(param, None)
    return urlunparse(parsed._replace(query=urlencode(query, doseq=True)))


def resolve(text: str, *, cookies_from_browser: str = "", extra_opts: dict | None = None) -> ResolvedSource:
    text = text.strip()
    if not text:
        raise ResolveError("empty link")
    if _VIDEO_ID.match(text):
        text = f"https://www.youtube.com/watch?v={text}"
    elif _BARE_CHANNEL.match(text):
        text = text.rstrip("/") + "/videos"
    else:
        text = _strip_playlist_context(text)

    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": "in_playlist",
        "playlist_items": "1-100000",
        "noplaylist": False,
    }
    if cookies_from_browser:
        opts["cookiesfrombrowser"] = (cookies_from_browser,)
    if extra_opts:
        opts.update(extra_opts)

    try:
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(text, download=False)
    except Exception as exc:
        raise ResolveError(str(exc)) from exc
    if info is None:
        raise ResolveError("nothing found at that link")

    if info.get("_type") in ("playlist", "multi_video") or "entries" in info:
        entries = [e for e in (info.get("entries") or []) if e]
        videos = [_mk_video(e) for e in entries if (e.get("id") or e.get("url"))]
        is_channel = (
            info.get("extractor", "").startswith("youtube:tab")
            and (info.get("channel_id") or "").startswith("UC")
            and "playlist" not in (info.get("webpage_url") or "")
        )
        kind = SourceKind.CHANNEL if is_channel else SourceKind.PLAYLIST
        return ResolvedSource(
            kind=kind,
            title=info.get("title") or info.get("channel") or "Playlist",
            url=info.get("webpage_url") or text,
            author=info.get("uploader") or info.get("channel") or "",
            thumbnail=_best_thumb(info) or (videos[0].thumbnail if videos else ""),
            videos=videos,
        )

    video = _mk_video(info)
    return ResolvedSource(
        kind=SourceKind.VIDEO,
        title=video.title,
        url=video.url,
        author=video.author,
        thumbnail=video.thumbnail,
        videos=[video],
    )
