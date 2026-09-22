"""Entry point for the ``ytpdl-web-bot`` Lambda function.

Telegram calls this URL (registered via ``setWebhook``) once per update —
one invocation per message/button-press, which is the natural fit for
Lambda (unlike ``bot/main.py``'s ``run_polling()``, a long-running loop that
needs an always-up process). See ``bot/lambda_webhook.py`` for the actual
command/callback logic.
"""

from __future__ import annotations

import asyncio
import json
import logging

from .bot.lambda_webhook import handle_update
from .config import TELEGRAM_WEBHOOK_SECRET

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("ytpdl.bot_lambda")


def handler(event: dict, context) -> dict:
    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    if TELEGRAM_WEBHOOK_SECRET and headers.get("x-telegram-bot-api-secret-token") != TELEGRAM_WEBHOOK_SECRET:
        log.warning("rejected webhook call with missing/invalid secret token")
        return {"statusCode": 401, "body": "unauthorized"}

    try:
        update = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return {"statusCode": 400, "body": "bad request"}

    try:
        asyncio.run(handle_update(update))
    except Exception:
        log.exception("failed to handle update: %s", update)
        # Still 200 — Telegram retries on non-2xx, and retrying a partially
        # handled update (e.g. a job already queued) would double-send.

    return {"statusCode": 200, "body": "ok"}
