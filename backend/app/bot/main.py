"""Telegram bot entry point.

Run with:  python -m app.bot.main

Talks to the SAME Redis job queue / job-events channel as the web app's API
and worker (see ``../main.py``, ``../worker.py``) — this process only
handles the Telegram side (commands, inline keyboards, message edits); the
actual yt-dlp work happens in the arq worker exactly like it does for web
users, so ``worker.py`` needs no changes at all to serve both.
"""

from __future__ import annotations

import logging

from telegram.ext import ApplicationBuilder, CallbackQueryHandler, CommandHandler, MessageHandler, filters

from ..config import TELEGRAM_BOT_TOKEN, TELEGRAM_LOCAL_API_URL, TELEGRAM_UPLOAD_TIMEOUT_SECONDS, ensure_dirs
from . import handlers, progress

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("ytpdl.bot")


async def _post_init(application) -> None:
    ensure_dirs()
    # Keep a strong reference in bot_data — asyncio only holds a *weak*
    # reference to a task via the event loop, so a fire-and-forget
    # `create_task(...)` with nothing else pointing at it is eligible for
    # garbage collection the moment this function returns. That silently
    # killed the progress listener minutes into the first live test: jobs
    # kept completing, nothing was ever sent back, no error either.
    application.bot_data["progress_task"] = application.create_task(progress.run(application.bot))


def main() -> None:
    if not TELEGRAM_BOT_TOKEN:
        raise SystemExit("TELEGRAM_BOT_TOKEN is not set — get one from @BotFather and set it in the environment.")

    builder = (
        ApplicationBuilder()
        .token(TELEGRAM_BOT_TOKEN)
        .post_init(_post_init)
        # PTB's defaults are 5s read/write/connect and 20s for media uploads
        # specifically — fine for plain API calls, nowhere near enough for a
        # video/audio file on anything but a fast link. This is what caused
        # send_video to fail with TimedOut in local testing (measured upload
        # throughput to Telegram was as low as ~75 KB/s on that connection).
        .read_timeout(TELEGRAM_UPLOAD_TIMEOUT_SECONDS)
        .write_timeout(TELEGRAM_UPLOAD_TIMEOUT_SECONDS)
        .media_write_timeout(TELEGRAM_UPLOAD_TIMEOUT_SECONDS)
        .connect_timeout(30)
        .pool_timeout(30)
    )
    if TELEGRAM_LOCAL_API_URL:
        builder = (
            builder.base_url(f"{TELEGRAM_LOCAL_API_URL}/bot")
            .base_file_url(f"{TELEGRAM_LOCAL_API_URL}/file/bot")
            .local_mode(True)
        )
    app = builder.build()

    app.add_handler(CommandHandler("start", handlers.start))
    app.add_handler(CommandHandler("help", handlers.start))
    app.add_handler(CommandHandler("jobs", handlers.cmd_jobs))
    app.add_handler(CommandHandler("subscribe", handlers.cmd_subscribe))
    app.add_handler(CommandHandler("subscriptions", handlers.cmd_subscriptions))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.handle_link))
    app.add_handler(CallbackQueryHandler(handlers.handle_callback))

    log.info("starting bot (local_mode=%s)", bool(TELEGRAM_LOCAL_API_URL))
    app.run_polling(allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    main()
