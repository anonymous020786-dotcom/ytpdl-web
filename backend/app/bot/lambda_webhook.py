"""Telegram webhook update handling for the Lambda deployment.

Mirrors ``handlers.py``'s behavior (same commands, same flow, same Redis
state via ``store``/``state``) but against a plain Telegram update dict and
``telegram_client``'s HTTP calls instead of python-telegram-bot's
``Application``/``Update``/``CallbackContext`` objects, which assume a
long-running dispatcher process rather than one-invocation-per-update.
``handlers.py`` itself is untouched and still used by the polling
(docker-compose) deployment.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid

from .. import store
from ..config import DEFAULT_SUBSCRIPTION_INTERVAL_MINUTES, WORKER_LAMBDA_NAME, AWS_REGION, pot_extractor_args
from ..core import resolver
from ..core.settings import DownloadSettings
from ..core.subscriptions import Subscription
from . import state, telegram_client as tg

log = logging.getLogger("ytpdl.bot.lambda_webhook")

_WELCOME = (
    "Send me a YouTube video, playlist, or channel link and I'll download it.\n\n"
    "Commands:\n"
    "/subscribe <link> — get the file automatically whenever a channel/playlist has a new upload\n"
    "/subscriptions — manage your subscriptions\n"
    "/jobs — your recent downloads"
)


def _owner_id(chat_id: int) -> str:
    return f"tg:{chat_id}"


def _invoke_worker(action: str, payload: dict) -> None:
    import json as _json

    import boto3

    client = boto3.client("lambda", region_name=AWS_REGION)
    client.invoke(
        FunctionName=WORKER_LAMBDA_NAME,
        InvocationType="Event",
        Payload=_json.dumps({"action": action, **payload}).encode(),
    )


async def handle_update(update: dict) -> None:
    if "message" in update:
        await _handle_message(update["message"])
    elif "callback_query" in update:
        await _handle_callback(update["callback_query"])


async def _handle_message(message: dict) -> None:
    chat = message.get("chat") or {}
    if chat.get("type") != "private":
        return  # DMs only, same as handlers.py::_is_private
    chat_id = chat["id"]
    text = (message.get("text") or "").strip()

    if text in ("/start", "/help"):
        await tg.asend_message(chat_id, _WELCOME)
        return
    if text == "/jobs":
        await _cmd_jobs(chat_id)
        return
    if text.startswith("/subscribe"):
        await _cmd_subscribe(chat_id, text)
        return
    if text == "/subscriptions":
        await _cmd_subscriptions(chat_id)
        return
    if text.startswith("/"):
        return  # unknown command — ignore rather than error

    await _handle_link(chat_id, text)


async def _cmd_jobs(chat_id: int) -> None:
    owner_id = _owner_id(chat_id)
    r = store.async_client()
    try:
        jobs = await store.list_jobs(r, owner_id=owner_id, limit=10)
    finally:
        await r.close()

    if not jobs:
        await tg.asend_message(chat_id, "No downloads yet — paste a link to get started.")
        return
    lines = [
        f"• {j.get('title') or j['job_id']} — {j.get('state')} ({j.get('done', '0')}/{j.get('total', '0')})"
        for j in jobs
    ]
    await tg.asend_message(chat_id, "\n".join(lines))


async def _cmd_subscribe(chat_id: int, text: str) -> None:
    args = text.split()[1:]
    if not args:
        await tg.asend_message(chat_id, "Usage: /subscribe <channel or playlist link> [interval minutes]")
        return

    url = args[0]
    interval = DEFAULT_SUBSCRIPTION_INTERVAL_MINUTES
    if len(args) > 1 and args[1].isdigit():
        interval = int(args[1])

    sent = await tg.asend_message(chat_id, "🔎 Resolving…")
    msg_id = sent.get("result", {}).get("message_id")
    try:
        source = await asyncio.to_thread(resolver.resolve, url, extra_opts=pot_extractor_args())
    except resolver.ResolveError as exc:
        await tg.aedit_message_text(chat_id, msg_id, f"❌ Couldn't resolve that link: {exc}")
        return

    sub_id = uuid.uuid4().hex[:12]
    ids = [v.id for v in source.videos if v.id]
    owner_id = _owner_id(chat_id)
    sub = Subscription(
        id=sub_id, owner_id=owner_id, url=url, title=source.title, kind=source.kind.value,
        interval_minutes=interval, known_ids=ids[:500], last_checked=time.time(),
    )
    r = store.async_client()
    try:
        await store.create_subscription(
            r, sub_id, owner_id=owner_id, url=url, title=source.title, kind=source.kind.value,
            interval_minutes=interval,
        )
        await store.save_subscription(r, sub)
    finally:
        await r.close()

    await tg.aedit_message_text(
        chat_id, msg_id,
        f'✅ Subscribed to "{source.title}" — checking every {interval} min. '
        "New uploads get downloaded and sent to you automatically.",
    )


async def _cmd_subscriptions(chat_id: int) -> None:
    owner_id = _owner_id(chat_id)
    r = store.async_client()
    try:
        subs = await store.list_subscriptions(r, owner_id=owner_id)
    finally:
        await r.close()

    if not subs:
        await tg.asend_message(chat_id, "No subscriptions yet. /subscribe <link> to add one.")
        return
    for s in subs:
        await tg.asend_message(
            chat_id,
            f"{s.title or s.url}\n{s.kind} · every {s.interval_minutes}m · {len(s.known_ids)} known videos",
            reply_markup=tg.subscription_row(s.id),
        )


async def _handle_link(chat_id: int, text: str) -> None:
    if not resolver.looks_like_youtube(text):
        await tg.asend_message(chat_id, "That doesn't look like a YouTube link — paste a video, playlist, or channel URL.")
        return

    sent = await tg.asend_message(chat_id, "🔎 Resolving…")
    msg_id = sent.get("result", {}).get("message_id")
    try:
        source = await asyncio.to_thread(resolver.resolve, text, extra_opts=pot_extractor_args())
    except resolver.ResolveError as exc:
        await tg.aedit_message_text(chat_id, msg_id, f"❌ Couldn't resolve that link: {exc}")
        return

    r = state.client()
    try:
        await state.save_pending(r, chat_id, source=source.to_dict())
    finally:
        await r.close()

    count = len(source.videos)
    summary = f"{source.title}\n{source.kind} · {count} item{'s' if count != 1 else ''}\n\nDownload as:"
    await tg.aedit_message_text(chat_id, msg_id, summary, reply_markup=tg.kind_choice())


async def _start_download(chat_id: int, message_id: int, **settings_kwargs) -> None:
    r = state.client()
    try:
        pending = await state.load_pending(r, chat_id)
        if pending is None:
            await tg.aedit_message_text(chat_id, message_id, "That selection expired — paste the link again.")
            return
        source_dict = pending["source"]
        await state.clear_pending(r, chat_id)
    finally:
        await r.close()

    settings = DownloadSettings(**settings_kwargs)
    job_id = uuid.uuid4().hex[:12]
    owner_id = _owner_id(chat_id)

    r2 = store.async_client()
    try:
        await store.create_job_record(
            r2, job_id, owner_id=owner_id, title=source_dict.get("title", ""),
            kind=source_dict.get("kind", "video"), total=len(source_dict.get("videos", [])),
        )
    finally:
        await r2.close()

    r3 = state.client()
    try:
        await state.save_job_message(r3, job_id, chat_id=chat_id, message_id=message_id)
    finally:
        await r3.close()

    _invoke_worker(
        "run_download_job",
        {"job_id": job_id, "source": source_dict, "settings": settings.to_dict(), "owner_id": owner_id},
    )

    await tg.aedit_message_text(chat_id, message_id, "⏳ Queued…", reply_markup=tg.job_controls(job_id, paused=False))


async def _handle_callback(cq: dict) -> None:
    cq_id = cq["id"]
    data = cq.get("data") or ""
    message = cq.get("message") or {}
    chat_id = message.get("chat", {}).get("id")
    message_id = message.get("message_id")
    await tg.aanswer_callback_query(cq_id)

    if data == "abort":
        r = state.client()
        try:
            await state.clear_pending(r, chat_id)
        finally:
            await r.close()
        await tg.aedit_message_text(chat_id, message_id, "Cancelled.")
        return

    if data.startswith("kind:"):
        kind = data.split(":", 1)[1]
        r = state.client()
        try:
            pending = await state.load_pending(r, chat_id)
        finally:
            await r.close()
        if pending is None:
            await tg.aedit_message_text(chat_id, message_id, "That selection expired — paste the link again.")
            return
        if kind == "audio":
            await tg.aedit_message_text(chat_id, message_id, "Pick a format:", reply_markup=tg.audio_format_choice())
        else:
            await tg.aedit_message_text(chat_id, message_id, "Pick a quality:", reply_markup=tg.video_quality_choice())
        return

    if data.startswith("afmt:"):
        fmt = data.split(":", 1)[1]
        await _start_download(chat_id, message_id, audio_only=True, audio_format=fmt)
        return

    if data.startswith("quality:"):
        quality = data.split(":", 1)[1]
        r = state.client()
        try:
            pending = await state.load_pending(r, chat_id)
            if pending is None:
                await tg.aedit_message_text(chat_id, message_id, "That selection expired — paste the link again.")
                return
            pending.setdefault("settings", {})["quality"] = quality
            await state.save_pending(r, chat_id, source=pending["source"], settings=pending["settings"])
        finally:
            await r.close()
        await tg.aedit_message_text(chat_id, message_id, "Pick a container format:", reply_markup=tg.video_format_choice())
        return

    if data.startswith("vfmt:"):
        fmt = data.split(":", 1)[1]
        r = state.client()
        try:
            pending = await state.load_pending(r, chat_id)
        finally:
            await r.close()
        quality = (pending or {}).get("settings", {}).get("quality", "1080")
        await _start_download(chat_id, message_id, audio_only=False, quality=quality, video_format=fmt, convert=True)
        return

    if data.startswith("pause:"):
        job_id = data.split(":", 1)[1]
        r = store.async_client()
        try:
            await store.request_pause(r, job_id)
        finally:
            await r.close()
        return

    if data.startswith("resume:"):
        job_id = data.split(":", 1)[1]
        r = store.async_client()
        try:
            await store.request_resume(r, job_id)
        finally:
            await r.close()
        return

    if data.startswith("cancel:"):
        job_id = data.split(":", 1)[1]
        r = store.async_client()
        try:
            await store.request_cancel(r, job_id)
        finally:
            await r.close()
        return

    if data.startswith("subcheck:"):
        sub_id = data.split(":", 1)[1]
        _invoke_worker("check_one_subscription", {"sub_id": sub_id})
        return

    if data.startswith("subdel:"):
        sub_id = data.split(":", 1)[1]
        r = store.async_client()
        try:
            await store.delete_subscription(r, sub_id)
        finally:
            await r.close()
        await tg.aedit_message_text(chat_id, message_id, "Removed.")
        return

    log.warning("unhandled callback data: %s", data)
