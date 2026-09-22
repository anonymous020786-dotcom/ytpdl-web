"""Sync Telegram progress relay for the Lambda worker.

``progress.py`` does the same job (job-events -> message edits -> file
delivery) but as a persistent Redis pub/sub listener, which doesn't exist in
Lambda — there's no process running between invocations for it to be. The
worker Lambda already runs synchronously for a job's whole duration, so it
relays progress for its own job directly instead, using the same throttling/
rendering rules as ``progress.py`` so the chat experience matches.
"""

from __future__ import annotations

import logging
import time

from . import state, telegram_client as tg

log = logging.getLogger("ytpdl.bot.relay")

_EDIT_INTERVAL = 3.0  # seconds — stay well under Telegram's per-chat edit rate limit


def owner_chat_id(owner_id: str) -> int | None:
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


class TelegramRelay:
    """One instance per job; call ``on_event`` from the job's ``publish``
    callback. Looks the job's (chat_id, message_id) up once and caches it —
    ``_start_download`` (bot/lambda_webhook.py) always saves it before the
    worker Lambda is invoked, so it's expected to already be there."""

    def __init__(self, job_id: str, chat_id: int) -> None:
        self.job_id = job_id
        self.chat_id = chat_id
        self.message_id: int | None = None
        self._last_edit_at = 0.0
        self._last_text = ""
        r = state.sync_client()
        try:
            found = state.sync_get_job_message(r, job_id)
        finally:
            r.close()
        if found:
            self.message_id = found[1]

    def on_event(self, event: dict) -> None:
        if self.message_id is None:
            return  # nowhere to relay to — shouldn't happen, see NOTE above

        event_state = event.get("state")
        if event_state == "failed":
            self._reset()
            self._safe_edit(f"❌ Failed: {event.get('error') or 'unknown error'}")
            return
        if event_state == "cancelled":
            self._reset()
            self._safe_edit("✖ Cancelled")
            return
        if event.get("type") == "finished":
            return  # "completed" is handled by the caller after S3 upload, once file URLs are known

        text = _render(event)
        if self._last_text == text:
            return
        now = time.monotonic()
        is_state_change = event.get("type") == "state"
        if not is_state_change and now - self._last_edit_at < _EDIT_INTERVAL:
            return
        self._last_edit_at = now
        self._last_text = text
        markup = tg.job_controls(self.job_id, paused=event_state == "paused")
        self._safe_edit(text, markup)

    def deliver(self, files: list[dict], presigned_url_fn) -> None:
        """Called once the worker has uploaded the finished file(s) to S3.
        ``presigned_url_fn(key, filename) -> url``; Telegram fetches the
        file server-side from that URL, no re-upload through this Lambda."""
        if self.message_id is None:
            return
        if not files:
            self._safe_edit("✅ Done, but no output file was found.")
            return
        self._safe_edit(f"✅ Done — sending {len(files)} file(s)…")
        for f in files:
            url = presigned_url_fn(f["key"], f["name"])
            self._send_file(f["name"], url)

    def _send_file(self, name: str, url: str) -> None:
        ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
        try:
            if ext in {"mp3", "m4a", "opus", "flac", "wav", "ogg", "aac"}:
                resp = tg.send_audio(self.chat_id, url, caption=name)
            else:
                resp = tg.send_video(self.chat_id, url, caption=name)
            if not resp.get("ok"):
                resp = tg.send_document(self.chat_id, url, caption=name)
                if not resp.get("ok"):
                    tg.send_message(self.chat_id, f'❌ Couldn\'t send "{name}"')
        except Exception:
            log.exception("failed to deliver %s for job %s", name, self.job_id)
            tg.send_message(self.chat_id, f'❌ Couldn\'t send "{name}"')

    def _safe_edit(self, text: str, markup: dict | None = None) -> None:
        tg.edit_message_text(self.chat_id, self.message_id, text, reply_markup=markup)

    def _reset(self) -> None:
        self._last_edit_at = 0.0
        self._last_text = ""
