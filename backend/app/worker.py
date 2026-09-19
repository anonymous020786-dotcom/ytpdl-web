"""arq worker: runs one ``DownloadRunner`` per job.

yt-dlp's ``download()`` is blocking, so each job runs in a thread via
``run_in_executor`` — arq's own concurrency (``max_jobs``) is what actually
caps how many downloads run at once (mirrors the desktop app's
``QThreadPool.setMaxThreadCount``). The thread talks back to Redis with a
plain sync client; the FastAPI process picks those events up over pub/sub and
fans them out to WebSocket clients (see ``main.py``).

Run with:  arq app.worker.WorkerSettings
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid

from arq import cron
from arq.connections import RedisSettings

from . import store
from .config import (
    DEFAULT_SUBSCRIPTION_INTERVAL_MINUTES,
    MAX_CONCURRENT_DOWNLOADS,
    RATE_LIMIT_KIB,
    REDIS_URL,
    WORK_ROOT,
    DOWNLOAD_ROOT,
    ensure_dirs,
)
from .core import resolver
from .core.models import ResolvedSource
from .core.settings import DownloadSettings
from .core.subscriptions import Subscription, diff_new_ids
from .jobs import DownloadRunner
from .store import sync_client, sync_is_cancelled, sync_is_paused, sync_publish_event

log = logging.getLogger(__name__)


async def run_download_job(ctx, job_id: str, source_dict: dict, settings_dict: dict, owner_id: str) -> None:
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, _run_blocking, job_id, source_dict, settings_dict, owner_id)


def _run_blocking(job_id: str, source_dict: dict, settings_dict: dict, owner_id: str) -> None:
    client = sync_client()

    def publish(event: dict) -> None:
        # owner_id rides along on every event so the API process's pub/sub
        # bridge can route it to only that user's WebSocket connections.
        sync_publish_event(client, {**event, "owner_id": owner_id})

    try:
        source = ResolvedSource.from_dict(source_dict)
        settings = DownloadSettings.from_dict(settings_dict)
        runner = DownloadRunner(
            job_id,
            source,
            settings,
            work_root=WORK_ROOT,
            dest_root=DOWNLOAD_ROOT,
            publish=publish,
            is_cancelled=lambda: sync_is_cancelled(client, job_id),
            is_paused=lambda: sync_is_paused(client, job_id),
            rate_limit_kib=RATE_LIMIT_KIB,
        )
        runner.run()
    finally:
        client.close()


async def check_due_subscriptions(ctx) -> None:
    """Runs every minute (see ``cron_jobs`` below); skips any subscription
    whose own ``interval_minutes`` hasn't elapsed since its last check."""
    client = store.async_client()
    try:
        now = time.time()
        for sub in await store.list_subscriptions(client):
            interval = sub.interval_minutes or DEFAULT_SUBSCRIPTION_INTERVAL_MINUTES
            if now - sub.last_checked < interval * 60:
                continue
            await _check_subscription(ctx, client, sub)
    finally:
        await client.close()


async def _check_subscription(ctx, client, sub: Subscription) -> None:
    loop = asyncio.get_running_loop()
    try:
        source = await loop.run_in_executor(None, resolver.resolve, sub.url)
    except resolver.ResolveError as exc:
        log.warning("subscription check failed for %s: %s", sub.url, exc)
        sub.last_checked = time.time()
        await store.save_subscription(client, sub)
        return

    ids = [v.id for v in source.videos if v.id]
    new_ids = diff_new_ids(sub, ids)

    if new_ids:
        new_id_set = set(new_ids)
        new_videos = [v for v in source.videos if v.id in new_id_set]
        job_source = ResolvedSource(
            kind=source.kind,
            title=source.title,
            url=source.url,
            author=source.author,
            thumbnail=source.thumbnail,
            videos=new_videos,
        )
        job_id = uuid.uuid4().hex[:12]
        await store.create_job_record(
            client,
            job_id,
            owner_id=sub.owner_id,
            title=f"{source.title} — new uploads",
            kind=source.kind.value,
            total=len(new_videos),
        )
        await ctx["redis"].enqueue_job(
            "run_download_job",
            job_id,
            job_source.to_dict(),
            DownloadSettings().to_dict(),
            sub.owner_id,
            _job_id=job_id,
        )
        log.info("subscription %s: queued %d new video(s) as job %s", sub.id, len(new_videos), job_id)

    sub.title = source.title or sub.title
    sub.new_count = 0  # any "new" videos were auto-queued above, not left dangling for a UI badge
    sub.known_ids = ids[:500]
    sub.last_checked = time.time()
    await store.save_subscription(client, sub)


async def check_one_subscription(ctx, sub_id: str) -> None:
    """Manual "check now" — bypasses the interval gate that check_due_subscriptions applies."""
    client = store.async_client()
    try:
        sub = await store.get_subscription(client, sub_id)
        if sub is None:
            return
        await _check_subscription(ctx, client, sub)
    finally:
        await client.close()


async def startup(ctx) -> None:
    ensure_dirs()


async def shutdown(ctx) -> None:
    pass


class WorkerSettings:
    functions = [run_download_job, check_one_subscription]
    cron_jobs = [cron(check_due_subscriptions, minute=set(range(60)))]
    redis_settings = RedisSettings.from_dsn(REDIS_URL)
    max_jobs = MAX_CONCURRENT_DOWNLOADS
    on_startup = startup
    on_shutdown = shutdown
