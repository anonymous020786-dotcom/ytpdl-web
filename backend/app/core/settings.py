"""Typed download settings, shared between the API schema and the job runner.

Trimmed from the desktop app's ``ytpdl/core/settings.py``: this keeps
``DownloadSettings`` (per-job options) unchanged since it has no Qt
dependency, but drops ``AppSettings``/``SettingsStore`` — in the web app,
app-wide preferences (concurrency, rate limit) are server config (env vars),
not a per-client JSON file.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field, fields
from typing import Any


@dataclass
class DownloadSettings:
    save_path: str = ""  # ignored by the web job runner; destination is server-controlled
    audio_only: bool = False
    audio_format: str = "mp3"
    video_format: str = "mkv"
    quality: str = "1080"  # target height in pixels, as a string
    prefer_highest_fps: bool = False
    convert: bool = False
    set_bitrate: bool = False
    bitrate: str = "192"  # kbit/s for audio re-encode

    download_subtitles: bool = False
    auto_subtitles: bool = False
    subtitle_languages: str = "en"
    embed_subtitles: bool = True

    separate_playlist_folders: bool = True
    open_folder_when_done: bool = False
    skip_existing: bool = False
    tag_audio: bool = True
    embed_thumbnail: bool = True

    use_subset: bool = False
    subset_start: int = 1
    subset_end: int = 0  # 0 == until the end

    filter_by_length: bool = False
    filter_longer_than: bool = False  # False => "shorter than"
    filter_minutes: float = 4.0

    filename_template: str = "$title"
    audio_language: str = "default"

    def clone(self) -> DownloadSettings:
        return dataclasses.replace(self)

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DownloadSettings:
        return _coerce(cls, data)


def _coerce(cls, data: dict[str, Any]):
    """Build a dataclass from a dict, ignoring unknown keys and fixing types."""
    kwargs: dict[str, Any] = {}
    valid = {f.name: f for f in fields(cls)}
    for name, f in valid.items():
        if name not in data:
            continue
        value = data[name]
        try:
            if f.type in ("bool", bool):
                value = bool(value)
            elif f.type in ("int", int):
                value = int(value)
            elif f.type in ("float", float):
                value = float(value)
            elif f.type in ("str", str):
                value = str(value)
        except (TypeError, ValueError):
            continue
        kwargs[name] = value
    return cls(**kwargs)
