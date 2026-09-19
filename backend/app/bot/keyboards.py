"""Inline keyboard builders for the download flow and job/subscription controls."""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

AUDIO_FORMATS = ["mp3", "m4a", "opus", "flac"]
VIDEO_QUALITIES = ["480", "720", "1080", "2160"]
VIDEO_FORMATS = ["mp4", "mkv", "webm"]


def kind_choice() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🎵 Audio only", callback_data="kind:audio"),
                InlineKeyboardButton("🎬 Video", callback_data="kind:video"),
            ],
            [InlineKeyboardButton("✖ Cancel", callback_data="abort")],
        ]
    )


def audio_format_choice() -> InlineKeyboardMarkup:
    row = [InlineKeyboardButton(f.upper(), callback_data=f"afmt:{f}") for f in AUDIO_FORMATS]
    return InlineKeyboardMarkup([row, [InlineKeyboardButton("✖ Cancel", callback_data="abort")]])


def video_quality_choice() -> InlineKeyboardMarkup:
    row = [InlineKeyboardButton(f"{q}p", callback_data=f"quality:{q}") for q in VIDEO_QUALITIES]
    return InlineKeyboardMarkup([row, [InlineKeyboardButton("✖ Cancel", callback_data="abort")]])


def video_format_choice() -> InlineKeyboardMarkup:
    row = [InlineKeyboardButton(f.upper(), callback_data=f"vfmt:{f}") for f in VIDEO_FORMATS]
    return InlineKeyboardMarkup([row, [InlineKeyboardButton("✖ Cancel", callback_data="abort")]])


def job_controls(job_id: str, *, paused: bool) -> InlineKeyboardMarkup:
    toggle = InlineKeyboardButton("▶ Resume", callback_data=f"resume:{job_id}") if paused else InlineKeyboardButton(
        "⏸ Pause", callback_data=f"pause:{job_id}"
    )
    return InlineKeyboardMarkup([[toggle, InlineKeyboardButton("✖ Cancel", callback_data=f"cancel:{job_id}")]])


def subscription_row(sub_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🔄 Check now", callback_data=f"subcheck:{sub_id}"),
                InlineKeyboardButton("🗑 Remove", callback_data=f"subdel:{sub_id}"),
            ]
        ]
    )
