"""Entry point for the ``ytpdl-web-worker`` Lambda function.

Replaces arq's persistent Redis-polling worker (there's nothing to poll
between invocations in Lambda) — the API Lambda asynchronously invokes this
function directly (``lambda:InvokeFunction``, ``InvocationType=Event``) in
place of ``arq_pool.enqueue_job``, and EventBridge invokes it on a schedule
for the subscription-check cron. See ``main.py``'s ``_invoke_worker_lambda``
and ``worker.py`` for the actual job logic, which is unchanged from the
arq path — only how a job gets started differs.
"""

from __future__ import annotations

import asyncio
import logging

from . import worker
from .config import ensure_dirs

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("ytpdl.worker_lambda")


def handler(event: dict, context) -> dict:
    ensure_dirs()
    action = event.get("action", "")
    log.info("worker lambda invoked: action=%s", action)

    if action == "run_download_job":
        worker._run_blocking(event["job_id"], event["source"], event["settings"], event["owner_id"])
    elif action == "check_one_subscription":
        asyncio.run(worker.check_one_subscription({}, event["sub_id"]))
    elif action == "check_due_subscriptions":
        asyncio.run(worker.check_due_subscriptions({}))
    else:
        log.warning("unknown worker action: %r", action)
        return {"ok": False, "error": f"unknown action {action!r}"}

    return {"ok": True}
