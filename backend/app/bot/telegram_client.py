"""Plain stdlib HTTP client for the Telegram Bot API.

Used by the Lambda deployment instead of python-telegram-bot: PTB's
``Application``/dispatcher model assumes a long-running process (polling or
an always-up webhook server), which doesn't fit Lambda's one-invocation-per-
update model, and pulling in PTB just for its thin wrappers around a handful
of REST calls isn't worth the deployment-package size. Bot API methods used
here (sendMessage, editMessageText, sendVideo/Audio/Document with a URL,
answerCallbackQuery, setWebhook) are plain JSON-over-HTTPS — no SDK needed.

Every function has a sync core (used by worker.py, which runs in a plain
thread, not an event loop) and an async wrapper (used by the webhook
handler) via ``asyncio.to_thread``, mirroring how ``resolver.resolve`` is
wrapped elsewhere in this codebase rather than adding an async HTTP
dependency just for this.
"""

from __future__ import annotations

import asyncio
import json
import logging
import urllib.error
import urllib.request

from ..config import TELEGRAM_BOT_TOKEN

log = logging.getLogger("ytpdl.bot.telegram_client")


def _api_base() -> str:
    return f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"


def call(method: str, **params) -> dict:
    """Sync core: one Bot API call, JSON in, JSON out. Raises on a non-2xx
    response except the extremely common "message is not modified" edit
    no-op, which callers shouldn't have to special-case themselves."""
    body = json.dumps({k: v for k, v in params.items() if v is not None}).encode()
    req = urllib.request.Request(
        f"{_api_base()}/{method}", data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        payload = exc.read().decode(errors="replace")
        if "not modified" in payload.lower():
            return {"ok": True, "skipped": "not modified"}
        log.warning("Telegram API %s failed: %s %s", method, exc.code, payload)
        return {"ok": False, "error": payload}


async def acall(method: str, **params) -> dict:
    return await asyncio.to_thread(call, method, **params)


# -- convenience wrappers, sync -------------------------------------------------
def send_message(chat_id: int, text: str, *, reply_markup: dict | None = None) -> dict:
    return call("sendMessage", chat_id=chat_id, text=text, reply_markup=reply_markup)


def edit_message_text(chat_id: int, message_id: int, text: str, *, reply_markup: dict | None = None) -> dict:
    return call("editMessageText", chat_id=chat_id, message_id=message_id, text=text, reply_markup=reply_markup)


def answer_callback_query(callback_query_id: str, text: str | None = None) -> dict:
    return call("answerCallbackQuery", callback_query_id=callback_query_id, text=text)


def send_video(chat_id: int, url: str, *, caption: str | None = None) -> dict:
    return call("sendVideo", chat_id=chat_id, video=url, caption=caption, supports_streaming=True)


def send_audio(chat_id: int, url: str, *, caption: str | None = None) -> dict:
    return call("sendAudio", chat_id=chat_id, audio=url, caption=caption)


def send_document(chat_id: int, url: str, *, caption: str | None = None) -> dict:
    return call("sendDocument", chat_id=chat_id, document=url, caption=caption)


def set_webhook(url: str, *, secret_token: str) -> dict:
    return call("setWebhook", url=url, secret_token=secret_token, allowed_updates=["message", "callback_query"])


# -- convenience wrappers, async (webhook handler) -------------------------------
async def asend_message(chat_id: int, text: str, *, reply_markup: dict | None = None) -> dict:
    return await acall("sendMessage", chat_id=chat_id, text=text, reply_markup=reply_markup)


async def aedit_message_text(chat_id: int, message_id: int, text: str, *, reply_markup: dict | None = None) -> dict:
    return await acall("editMessageText", chat_id=chat_id, message_id=message_id, text=text, reply_markup=reply_markup)


async def aanswer_callback_query(callback_query_id: str, text: str | None = None) -> dict:
    return await acall("answerCallbackQuery", callback_query_id=callback_query_id, text=text)


# -- inline keyboards (plain dicts — see Telegram's InlineKeyboardMarkup spec) --
AUDIO_FORMATS = ["mp3", "m4a", "opus", "flac"]
VIDEO_QUALITIES = ["480", "720", "1080", "2160"]
VIDEO_FORMATS = ["mp4", "mkv", "webm"]


def _kb(rows: list[list[tuple[str, str]]]) -> dict:
    return {"inline_keyboard": [[{"text": t, "callback_data": d} for t, d in row] for row in rows]}


def kind_choice() -> dict:
    return _kb([[("🎵 Audio only", "kind:audio"), ("🎬 Video", "kind:video")], [("✖ Cancel", "abort")]])


def audio_format_choice() -> dict:
    return _kb([[(f.upper(), f"afmt:{f}") for f in AUDIO_FORMATS], [("✖ Cancel", "abort")]])


def video_quality_choice() -> dict:
    return _kb([[(f"{q}p", f"quality:{q}") for q in VIDEO_QUALITIES], [("✖ Cancel", "abort")]])


def video_format_choice() -> dict:
    return _kb([[(f.upper(), f"vfmt:{f}") for f in VIDEO_FORMATS], [("✖ Cancel", "abort")]])


def job_controls(job_id: str, *, paused: bool) -> dict:
    toggle = ("▶ Resume", f"resume:{job_id}") if paused else ("⏸ Pause", f"pause:{job_id}")
    return _kb([[toggle, ("✖ Cancel", f"cancel:{job_id}")]])


def subscription_row(sub_id: str) -> dict:
    return _kb([[("🔄 Check now", f"subcheck:{sub_id}"), ("🗑 Remove", f"subdel:{sub_id}")]])
