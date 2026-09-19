"""Command, message, and callback-query handlers.

A Telegram user is identified purely by their chat id — ``owner_id`` is
``"tg:<chat_id>"``, matching how the web app's job/subscription ownership
works (see ``store.py``), just with a different id namespace. There's no
account/login step; owning a Telegram account is the identity, same as any
other Telegram bot.

Jobs are enqueued onto the *same* arq queue the web app uses
(``run_download_job`` in ``worker.py``) — this process never runs yt-dlp
itself, it only talks to Telegram and to Redis.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid

from arq import create_pool
from arq.connections import RedisSettings
from telegram import Update
from telegram.ext import ContextTypes

from .. import store
from ..config import DEFAULT_SUBSCRIPTION_INTERVAL_MINUTES, REDIS_URL
from ..core import resolver
from ..core.settings import DownloadSettings
from ..core.subscriptions import Subscription
from . import keyboards, state

log = logging.getLogger("ytpdl.bot.handlers")

_WELCOME = (
    "Send me a YouTube video, playlist, or channel link and I'll download it.\n\n"
    "Commands:\n"
    "/subscribe <link> — get the file automatically whenever a channel/playlist has a new upload\n"
    "/subscriptions — manage your subscriptions\n"
    "/jobs — your recent downloads"
)


def _owner_id(chat_id: int) -> str:
    return f"tg:{chat_id}"


async def _arq_pool(context: ContextTypes.DEFAULT_TYPE):
    pool = context.bot_data.get("arq_pool")
    if pool is None:
        pool = await create_pool(RedisSettings.from_dsn(REDIS_URL))
        context.bot_data["arq_pool"] = pool
    return pool


def _is_private(update: Update) -> bool:
    # DMs only — keeps this a personal downloader per Telegram account rather
    # than a shared free-for-all in group chats.
    return update.effective_chat is not None and update.effective_chat.type == "private"


# -- commands -----------------------------------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(_WELCOME)


async def cmd_jobs(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_private(update):
        return
    owner_id = _owner_id(update.effective_chat.id)
    r = store.async_client()
    try:
        jobs = await store.list_jobs(r, owner_id=owner_id, limit=10)
    finally:
        await r.close()

    if not jobs:
        await update.message.reply_text("No downloads yet — paste a link to get started.")
        return
    lines = [
        f"• {j.get('title') or j['job_id']} — {j.get('state')} ({j.get('done', '0')}/{j.get('total', '0')})"
        for j in jobs
    ]
    await update.message.reply_text("\n".join(lines))


async def cmd_subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_private(update):
        return
    if not context.args:
        await update.message.reply_text("Usage: /subscribe <channel or playlist link> [interval minutes]")
        return

    url = context.args[0]
    interval = DEFAULT_SUBSCRIPTION_INTERVAL_MINUTES
    if len(context.args) > 1 and context.args[1].isdigit():
        interval = int(context.args[1])

    msg = await update.message.reply_text("🔎 Resolving…")
    try:
        source = await asyncio.to_thread(resolver.resolve, url)
    except resolver.ResolveError as exc:
        await msg.edit_text(f"❌ Couldn't resolve that link: {exc}")
        return

    sub_id = uuid.uuid4().hex[:12]
    ids = [v.id for v in source.videos if v.id]
    owner_id = _owner_id(update.effective_chat.id)
    sub = Subscription(
        id=sub_id,
        owner_id=owner_id,
        url=url,
        title=source.title,
        kind=source.kind.value,
        interval_minutes=interval,
        known_ids=ids[:500],
        last_checked=time.time(),
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

    await msg.edit_text(
        f'✅ Subscribed to "{source.title}" — checking every {interval} min. '
        "New uploads get downloaded and sent to you automatically."
    )


async def cmd_subscriptions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_private(update):
        return
    owner_id = _owner_id(update.effective_chat.id)
    r = store.async_client()
    try:
        subs = await store.list_subscriptions(r, owner_id=owner_id)
    finally:
        await r.close()

    if not subs:
        await update.message.reply_text("No subscriptions yet. /subscribe <link> to add one.")
        return
    for s in subs:
        await update.message.reply_text(
            f"{s.title or s.url}\n{s.kind} · every {s.interval_minutes}m · {len(s.known_ids)} known videos",
            reply_markup=keyboards.subscription_row(s.id),
        )


# -- link -> resolve -> pick format/quality -> queue --------------------------
async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_private(update):
        return
    text = (update.message.text or "").strip()
    if not resolver.looks_like_youtube(text):
        await update.message.reply_text(
            "That doesn't look like a YouTube link — paste a video, playlist, or channel URL."
        )
        return

    msg = await update.message.reply_text("🔎 Resolving…")
    try:
        source = await asyncio.to_thread(resolver.resolve, text)
    except resolver.ResolveError as exc:
        await msg.edit_text(f"❌ Couldn't resolve that link: {exc}")
        return

    r = state.client()
    try:
        await state.save_pending(r, update.effective_chat.id, source=source.to_dict())
    finally:
        await r.close()

    count = len(source.videos)
    summary = f"{source.title}\n{source.kind} · {count} item{'s' if count != 1 else ''}\n\nDownload as:"
    await msg.edit_text(summary, reply_markup=keyboards.kind_choice())


async def _start_download(query, context: ContextTypes.DEFAULT_TYPE, **settings_kwargs) -> None:
    chat_id = query.message.chat_id
    r = state.client()
    try:
        pending = await state.load_pending(r, chat_id)
        if pending is None:
            await query.edit_message_text("That selection expired — paste the link again.")
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

    pool = await _arq_pool(context)
    await pool.enqueue_job("run_download_job", job_id, source_dict, settings.to_dict(), owner_id, _job_id=job_id)

    await query.edit_message_text("⏳ Queued…", reply_markup=keyboards.job_controls(job_id, paused=False))

    r3 = state.client()
    try:
        await state.save_job_message(r3, job_id, chat_id=chat_id, message_id=query.message.message_id)
    finally:
        await r3.close()


# -- callback queries -----------------------------------------------------------
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data or ""
    chat_id = query.message.chat_id

    if data == "abort":
        r = state.client()
        try:
            await state.clear_pending(r, chat_id)
        finally:
            await r.close()
        await query.edit_message_text("Cancelled.")
        return

    if data.startswith("kind:"):
        kind = data.split(":", 1)[1]
        r = state.client()
        try:
            pending = await state.load_pending(r, chat_id)
        finally:
            await r.close()
        if pending is None:
            await query.edit_message_text("That selection expired — paste the link again.")
            return
        if kind == "audio":
            await query.edit_message_text("Pick a format:", reply_markup=keyboards.audio_format_choice())
        else:
            await query.edit_message_text("Pick a quality:", reply_markup=keyboards.video_quality_choice())
        return

    if data.startswith("afmt:"):
        fmt = data.split(":", 1)[1]
        await _start_download(query, context, audio_only=True, audio_format=fmt)
        return

    if data.startswith("quality:"):
        quality = data.split(":", 1)[1]
        r = state.client()
        try:
            pending = await state.load_pending(r, chat_id)
            if pending is None:
                await query.edit_message_text("That selection expired — paste the link again.")
                return
            pending["settings"]["quality"] = quality
            await state.save_pending(r, chat_id, source=pending["source"], settings=pending["settings"])
        finally:
            await r.close()
        await query.edit_message_text("Pick a container format:", reply_markup=keyboards.video_format_choice())
        return

    if data.startswith("vfmt:"):
        fmt = data.split(":", 1)[1]
        r = state.client()
        try:
            pending = await state.load_pending(r, chat_id)
        finally:
            await r.close()
        quality = (pending or {}).get("settings", {}).get("quality", "1080")
        await _start_download(query, context, audio_only=False, quality=quality, video_format=fmt, convert=True)
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
        pool = await _arq_pool(context)
        await pool.enqueue_job("check_one_subscription", sub_id)
        await query.answer("Checking…")
        return

    if data.startswith("subdel:"):
        sub_id = data.split(":", 1)[1]
        r = store.async_client()
        try:
            await store.delete_subscription(r, sub_id)
        finally:
            await r.close()
        await query.edit_message_text("Removed.")
        return

    log.warning("unhandled callback data: %s", data)
