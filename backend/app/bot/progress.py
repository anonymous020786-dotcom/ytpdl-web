"""Turns job-events Redis pub/sub messages into Telegram message edits, and
sends the finished file(s) on completion.

Subscribes to the exact same channel the web app's WebSocket bridge uses
(see ``main.py::_pubsub_bridge``) — this process and the web API can run at
the same time against the same Redis without interfering, each just filters
for the events relevant to it (``owner_id`` starting with ``"tg:"`` here).

A job with no tracked message yet (an auto-queued subscription download,
which nobody explicitly started from a chat) gets a fresh status message
sent the first time an event for it arrives, rather than requiring the
sender to have pre-created one.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from telegram import Bot
from telegram.error import BadRequest, TelegramError

from .. import store
from ..config import DOWNLOAD_ROOT, TELEGRAM_CLOUD_FILE_LIMIT_MB, TELEGRAM_LOCAL_MODE
from . import keyboards, state

log = logging.getLogger("ytpdl.bot.progress")

_EDIT_INTERVAL = 3.0  # seconds — stay well under Telegram's per-chat edit rate limit
_AUDIO_EXTS = {".mp3", ".m4a", ".opus", ".flac", ".wav", ".ogg", ".aac"}

_last_edit_at: dict[str, float] = {}
_last_text: dict[str, str] = {}


def _owner_chat_id(owner_id: str) -> int | None:
    if not owner_id.startswith("tg:"):
        return None
    try:
        return int(owner_id.split(":", 1)[1])
    except ValueError:
        return None


def _bar(percent: float, width: int = 12) -> str:
    filled = int(width * min(100.0, max(0.0, percent)) / 100)
    return "█" * filled + "░" * (width - filled)


def _render(event: dict) -> str:
    if event.get("state") == "paused":
        return "⏸ Paused"
    percent = float(event.get("percent") or 0)
    status = event.get("status") or event.get("state") or ""
    bits = [f"{_bar(percent)} {percent:.0f}%", status]
    if event.get("speed"):
        bits.append(str(event["speed"]))
    if event.get("eta"):
        bits.append(f"ETA {event['eta']}")
    return "\n".join(bits)


async def run(bot: Bot) -> None:
    client = store.async_client()
    pubsub = client.pubsub()
    await pubsub.subscribe(store.EVENTS_CHANNEL)
    log.info("progress listener subscribed to %s", store.EVENTS_CHANNEL)
    try:
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue
            try:
                await _handle_event(bot, json.loads(message["data"]))
            except Exception:
                log.exception("failed to handle job event: %s", message.get("data"))
    finally:
        await pubsub.unsubscribe(store.EVENTS_CHANNEL)
        await client.close()


async def _handle_event(bot: Bot, event: dict) -> None:
    chat_id = _owner_chat_id(event.get("owner_id", ""))
    if chat_id is None:
        return  # not a Telegram-owned job

    job_id = event["job_id"]
    r = state.client()
    try:
        mapping = await state.get_job_message(r, job_id)
        if mapping is None:
            msg = await bot.send_message(chat_id, "⏳ New upload found — downloading…")
            await state.save_job_message(r, job_id, chat_id=chat_id, message_id=msg.message_id)
            mapping = (chat_id, msg.message_id)
    finally:
        await r.close()

    _, message_id = mapping
    event_state = event.get("state")

    if event_state == "completed":
        _last_edit_at.pop(job_id, None)
        _last_text.pop(job_id, None)
        await _deliver(bot, chat_id, message_id, job_id)
        return
    if event_state == "failed":
        _last_edit_at.pop(job_id, None)
        _last_text.pop(job_id, None)
        await _safe_edit(bot, chat_id, message_id, f"❌ Failed: {event.get('error') or 'unknown error'}")
        return
    if event_state == "cancelled":
        _last_edit_at.pop(job_id, None)
        _last_text.pop(job_id, None)
        await _safe_edit(bot, chat_id, message_id, "✖ Cancelled")
        return

    text = _render(event)
    if _last_text.get(job_id) == text:
        return
    now = time.monotonic()
    is_state_change = event.get("type") == "state"
    if not is_state_change and now - _last_edit_at.get(job_id, 0) < _EDIT_INTERVAL:
        return
    _last_edit_at[job_id] = now
    _last_text[job_id] = text

    markup = keyboards.job_controls(job_id, paused=event_state == "paused")
    await _safe_edit(bot, chat_id, message_id, text, markup=markup)


async def _safe_edit(bot: Bot, chat_id: int, message_id: int, text: str, markup=None) -> None:
    try:
        await bot.edit_message_text(text, chat_id=chat_id, message_id=message_id, reply_markup=markup)
    except BadRequest as exc:
        if "not modified" not in str(exc).lower():
            log.warning("edit failed for job message in chat %s: %s", chat_id, exc)
    except TelegramError as exc:
        log.warning("telegram error editing message in chat %s: %s", chat_id, exc)


async def _deliver(bot: Bot, chat_id: int, message_id: int, job_id: str) -> None:
    job_dir = DOWNLOAD_ROOT / job_id
    files = sorted(p for p in job_dir.rglob("*") if p.is_file()) if job_dir.is_dir() else []
    if not files:
        await _safe_edit(bot, chat_id, message_id, "✅ Done, but no output file was found.")
        return

    await _safe_edit(bot, chat_id, message_id, f"✅ Done — sending {len(files)} file(s)…")
    for path in files:
        await _send_file(bot, chat_id, path)


def _open_ref(path: Path):
    return f"file://{path}" if TELEGRAM_LOCAL_MODE else path.open("rb")


async def _send_file(bot: Bot, chat_id: int, path: Path) -> None:
    size_mb = path.stat().st_size / 1_048_576
    if not TELEGRAM_LOCAL_MODE and size_mb > TELEGRAM_CLOUD_FILE_LIMIT_MB:
        await bot.send_message(
            chat_id,
            f'⚠ "{path.name}" is {size_mb:.0f}MB — too big to send here '
            f"(Telegram's {TELEGRAM_CLOUD_FILE_LIMIT_MB}MB limit without a local Bot API server).",
        )
        return

    is_audio = path.suffix.lower() in _AUDIO_EXTS
    try:
        file_ref = _open_ref(path)
        try:
            if is_audio:
                await bot.send_audio(chat_id, file_ref, filename=path.name)
            else:
                await bot.send_video(chat_id, file_ref, filename=path.name, supports_streaming=True)
        finally:
            if hasattr(file_ref, "close"):
                file_ref.close()
    except TelegramError as exc:
        log.warning("send failed for %s: %s — retrying as a generic document", path.name, exc)
        try:
            file_ref = _open_ref(path)
            try:
                await bot.send_document(chat_id, file_ref, filename=path.name)
            finally:
                if hasattr(file_ref, "close"):
                    file_ref.close()
        except TelegramError:
            log.exception("document fallback also failed for %s", path.name)
            await bot.send_message(chat_id, f'❌ Couldn\'t send "{path.name}": {exc}')
