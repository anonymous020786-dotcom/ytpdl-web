"""The download engine — web port of the desktop app's ``core/downloader.py``.

Same design (temp-then-move into a destination, filename templating, audio
tagging) with the Qt layer stripped out:

* ``JobSignals`` (Qt ``Signal``s) -> a plain ``publish(event: dict)`` callback,
  called from whatever thread yt-dlp's hooks fire on. The worker wires this to
  a Redis publish (see ``worker.py``) so the API process can fan progress out
  over WebSockets regardless of which worker process ran the job.
* the ``_cancelled``/``_paused`` instance flags -> ``is_cancelled()`` /
  ``is_paused()`` callbacks, since a job here runs in a different process
  than the one that might cancel or pause it (the API process reacts to an
  HTTP call; the flag is a Redis key the worker polls from inside
  ``_guard()``, called on every yt-dlp progress/postprocessor hook).
* ``QRunnable.run()`` -> a plain ``run()`` method called from a worker thread.

Every file lands under ``dest_root/<job_id>/...`` rather than a single shared
download folder, so concurrent jobs from different clients never collide and
each job's output is trivially listable/servable by job id.
"""

from __future__ import annotations

import logging
import re
import shutil
import time
from pathlib import Path
from typing import Callable

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadCancelled, DownloadError

from .core.ffmpeg import ffmpeg_dir
from .core.filenames import render_template
from .core.models import ResolvedSource, SourceKind
from .core.settings import DownloadSettings
from .core.tagging import tag_audio_file

log = logging.getLogger(__name__)

_ID_RE = re.compile(r"([A-Za-z0-9_-]{11})(?=\.[^.]+$|$)")
_AUDIO_CONTAINERS = {"mp3", "m4a", "aac", "opus", "flac", "wav", "ogg", "vorbis", "alac"}

PublishFn = Callable[[dict], None]
IsCancelledFn = Callable[[], bool]
IsPausedFn = Callable[[], bool]


class JobCancelled(Exception):
    pass


class DownloadRunner:
    def __init__(
        self,
        job_id: str,
        source: ResolvedSource,
        settings: DownloadSettings,
        *,
        work_root: Path,
        dest_root: Path,
        publish: PublishFn,
        is_cancelled: IsCancelledFn,
        is_paused: IsPausedFn | None = None,
        rate_limit_kib: int = 0,
        cookies_from_browser: str = "",
        extra_opts: dict | None = None,
    ) -> None:
        self.job_id = job_id
        self.source = source
        self.settings = settings
        self.rate_limit_kib = rate_limit_kib
        self.cookies_from_browser = cookies_from_browser
        self.extra_opts = extra_opts or {}
        self._publish = publish
        self._is_cancelled = is_cancelled
        self._is_paused = is_paused or (lambda: False)

        self.error = ""
        self.done_count = 0
        self.not_downloaded: list[tuple[str, str]] = []

        self._work_dir = work_root / job_id
        self._dest_dir = dest_root / job_id
        self._selected = self._select_videos()
        self._index_by_id = {v.id: i for i, v in enumerate(self._selected, start=1) if v.id}
        self.total = len(self._selected) or self.source.count
        self._target_is_audio = False

    # -- helpers -------------------------------------------------------------
    def _select_videos(self) -> list:
        s = self.settings
        videos = self.source.videos
        if not s.use_subset:
            return list(videos)
        start = max(1, s.subset_start)
        end = s.subset_end if s.subset_end else len(videos)
        return list(videos[start - 1 : end])

    def _emit(self, **event: object) -> None:
        self._publish({"job_id": self.job_id, **event})

    @property
    def destination(self) -> Path:
        base = self._dest_dir
        if self.settings.separate_playlist_folders and self.source.is_collection:
            base = base / _sanitize_dir(self.source.title)
        return base

    # -- yt-dlp option assembly --------------------------------------------
    def _build_opts(self) -> dict:
        s = self.settings
        opts: dict = {
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            "ignoreerrors": True,
            "outtmpl": {"default": str(self._work_dir / "%(playlist_index|1)s__%(id)s.%(ext)s")},
            "paths": {"home": str(self._work_dir)},
            "windowsfilenames": False,
            "retries": 5,
            "fragment_retries": 5,
            "progress_hooks": [self._progress_hook],
            "postprocessor_hooks": [self._pp_hook],
            "post_hooks": [self._post_hook],
        }

        location = ffmpeg_dir()
        if location:
            opts["ffmpeg_location"] = location

        if self.cookies_from_browser:
            opts["cookiesfrombrowser"] = (self.cookies_from_browser,)
        if self.rate_limit_kib > 0:
            opts["ratelimit"] = self.rate_limit_kib * 1024

        opts["noplaylist"] = True

        if s.filter_by_length:
            minutes = s.filter_minutes
            cmp = ">" if s.filter_longer_than else "<"
            opts["match_filter"] = _duration_filter(minutes * 60, cmp)

        pps: list[dict] = []
        target_is_audio = s.audio_only or (
            s.convert and s.audio_format in _AUDIO_CONTAINERS and not s.video_format
        )

        if s.audio_only:
            opts["format"] = _audio_format_string(s)
            pp = {"key": "FFmpegExtractAudio", "preferredcodec": _codec(s.audio_format)}
            if s.set_bitrate and s.bitrate.isdigit():
                pp["preferredquality"] = s.bitrate
            pps.append(pp)
        else:
            opts["format"] = _video_format_string(s)
            opts["merge_output_format"] = s.video_format
            if s.prefer_highest_fps:
                opts["format_sort"] = [f"res:{s.quality}", "fps", "vcodec:av01"]
            else:
                opts["format_sort"] = [f"res:{s.quality}"]
            if s.convert:
                pps.append({"key": "FFmpegVideoConvertor", "preferedformat": s.video_format})

        if s.audio_language and s.audio_language != "default":
            opts["format_sort"] = [f"lang:{s.audio_language}", *opts.get("format_sort", [])]

        if s.download_subtitles:
            opts["writesubtitles"] = True
            opts["writeautomaticsub"] = s.auto_subtitles
            opts["subtitleslangs"] = [x.strip() for x in s.subtitle_languages.split(",") if x.strip()] or ["en"]
            if s.embed_subtitles and not s.audio_only:
                pps.append({"key": "FFmpegEmbedSubtitle"})

        if s.embed_thumbnail:
            opts["writethumbnail"] = True
            pps.append({"key": "FFmpegThumbnailsConvertor", "format": "jpg", "when": "before_dl"})
            pps.append({"key": "EmbedThumbnail"})

        pps.append({"key": "FFmpegMetadata", "add_metadata": True})
        opts["postprocessors"] = pps
        self._target_is_audio = target_is_audio or s.audio_only
        if self.extra_opts:
            opts.update(self.extra_opts)
        return opts

    # -- hooks -------------------------------------------------------------
    def _guard(self) -> None:
        if self._is_cancelled():
            raise DownloadCancelled()
        if self._is_paused():
            self._emit(type="state", state="paused")
            while self._is_paused() and not self._is_cancelled():
                time.sleep(0.5)
            if self._is_cancelled():
                raise DownloadCancelled()
            self._emit(type="state", state="running")

    def _progress_hook(self, d: dict) -> None:
        self._guard()
        status = d.get("status")
        if status == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            got = d.get("downloaded_bytes") or 0
            pct = (got / total * 100) if total else 0.0
            title = (d.get("info_dict") or {}).get("title") or ""
            self._emit(
                type="progress",
                state="running",
                percent=pct,
                status=f"Downloading{f' — {title}' if title else ''}",
                speed=_fmt_speed(d.get("speed")),
                eta=_fmt_eta(d.get("eta")),
            )
        elif status == "finished":
            self._emit(type="progress", state="running", percent=100.0, status="Merging", speed="", eta="")

    def _pp_hook(self, d: dict) -> None:
        self._guard()
        if d.get("status") == "started":
            name = (d.get("postprocessor") or "").replace("FFmpeg", "")
            self._emit(type="progress", state="running", percent=100.0, status=f"Merging ({name})", speed="", eta="")

    def _post_hook(self, filepath: str) -> None:
        try:
            self._finalize_file(Path(filepath))
        except Exception as exc:
            log.exception("finalize failed for %s", filepath)
            self.not_downloaded.append((Path(filepath).name, str(exc)))

    def _finalize_file(self, src: Path) -> None:
        if not src.exists() or src.suffix.lower() in (".part", ".ytdl", ".webp", ".jpg", ".png"):
            return
        m = _ID_RE.search(src.name)
        vid_id = m.group(1) if m else ""
        index = self._index_by_id.get(vid_id, self.done_count + 1)
        video = next((v for v in self.source.videos if v.id == vid_id), None)

        dest_dir = self.destination
        dest_dir.mkdir(parents=True, exist_ok=True)

        if video is not None:
            stem = render_template(self.settings.filename_template, video, index, self.source.title)
        else:
            stem = src.stem.split("__", 1)[-1]

        target = _unique_path(dest_dir / f"{stem}{src.suffix}")
        shutil.move(str(src), str(target))

        if self.settings.tag_audio and self._target_is_audio and video is not None:
            tag_audio_file(target, video, index, self.source.title, self.source.author)

        self.done_count += 1
        self._emit(type="item_progress", done=self.done_count, total=self.total)

    # -- entry point ---------------------------------------------------------
    def run(self) -> None:
        self._emit(type="state", state="running")
        self._work_dir.mkdir(parents=True, exist_ok=True)
        try:
            opts = self._build_opts()
            self._emit(type="item_progress", done=0, total=self.total)
            if self.source.kind == SourceKind.VIDEO or not self._selected:
                targets = [self.source.url]
            else:
                targets = [v.url for v in self._selected if v.url]
            with YoutubeDL(opts) as ydl:
                ydl.download(targets)
        except DownloadCancelled:
            self._emit(type="finished", state="cancelled", error="")
            self._cleanup()
            return
        except (DownloadError, OSError) as exc:
            self.error = str(exc)
            self._emit(type="finished", state="failed", error=self.error)
            self._cleanup()
            return
        except Exception as exc:  # noqa: BLE001 - report, don't crash the worker
            log.exception("unexpected error in job %s", self.job_id)
            self.error = str(exc)
            self._emit(type="finished", state="failed", error=self.error)
            self._cleanup()
            return

        self._cleanup()
        if self._is_cancelled():
            self._emit(type="finished", state="cancelled", error="")
        elif self.not_downloaded and self.done_count == 0:
            self.error = "; ".join(f"{n}: {r}" for n, r in self.not_downloaded[:5])
            self._emit(type="finished", state="failed", error=self.error)
        else:
            self._emit(type="finished", state="completed", error="")

    def _cleanup(self) -> None:
        shutil.rmtree(self._work_dir, ignore_errors=True)


# -- module helpers -------------------------------------------------------------
def _sanitize_dir(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip().strip(".")[:120] or "playlist"


def _unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem, suffix, parent = path.stem, path.suffix, path.parent
    i = 1
    while True:
        candidate = parent / f"{stem}-{i}{suffix}"
        if not candidate.exists():
            return candidate
        i += 1


def _codec(fmt: str) -> str:
    return {"ogg": "vorbis"}.get(fmt, fmt)


def _audio_format_string(s: DownloadSettings) -> str:
    if s.audio_language and s.audio_language != "default":
        return f"bestaudio[language^={s.audio_language}]/bestaudio/best"
    return "bestaudio/best"


def _video_format_string(s: DownloadSettings) -> str:
    q = s.quality
    return f"bestvideo[height<=?{q}]+bestaudio/best[height<=?{q}]/best"


def _duration_filter(seconds: float, cmp: str):
    def _filter(info, *, incomplete=False):
        dur = info.get("duration")
        if dur is None:
            return None
        if cmp == ">" and dur > seconds:
            return None
        if cmp == "<" and dur < seconds:
            return None
        return f"video is {'shorter' if cmp == '>' else 'longer'} than the configured limit"

    return _filter


def _fmt_speed(speed: float | None) -> str:
    if not speed:
        return ""
    mib = speed / (1 << 20)
    if mib >= 1:
        return f"{mib:.2f} MiB/s"
    return f"{speed / 1024:.0f} KiB/s"


def _fmt_eta(eta: float | None) -> str:
    if not eta:
        return ""
    eta = int(eta)
    m, s = divmod(eta, 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"
