"""Redis-backed job state, shared between the API process and arq workers.

Job state lives in Redis, not Postgres, deliberately: jobs are ephemeral
(hours, not months — see ``JOB_TTL_HOURS``), and this keeps the scaffold to
one moving part. If you add user accounts / persistent history, that's the
signal to move job records into Postgres and keep Redis just for pub/sub +
the arq queue.

Key layout:
    job:{id}          hash  -- latest known state of one job
    jobs:index         zset  -- job id -> created_at unix timestamp, for listing
    cancel:{id}        string -- presence means "cancel this job", TTL'd
    pause:{id}         string -- presence means "pause this job", TTL'd
    sub:{id}           hash  -- one subscription (see core/subscriptions.py::Subscription)
    subs:index          set   -- subscription ids, for listing

Channel:
    job-events          pub/sub -- every state/progress update, for WebSocket fan-out
"""

from __future__ import annotations

import json
import time
from typing import Any

import redis as sync_redis
import redis.asyncio as async_redis

from .config import REDIS_URL
from .core.subscriptions import Subscription

EVENTS_CHANNEL = "job-events"
_CANCEL_TTL_SECONDS = 6 * 3600
_PAUSE_TTL_SECONDS = 6 * 3600


def _job_key(job_id: str) -> str:
    return f"job:{job_id}"


def _cancel_key(job_id: str) -> str:
    return f"cancel:{job_id}"


def _pause_key(job_id: str) -> str:
    return f"pause:{job_id}"


# -- sync (used inside the worker thread that runs yt-dlp) ------------------
def sync_client() -> sync_redis.Redis:
    return sync_redis.Redis.from_url(REDIS_URL, decode_responses=True)


def sync_publish_event(client: sync_redis.Redis, event: dict[str, Any]) -> None:
    job_id = event["job_id"]
    client.hset(_job_key(job_id), mapping=_flatten(event))
    client.publish(EVENTS_CHANNEL, json.dumps(event))


def sync_save_job_files(client: sync_redis.Redis, job_id: str, files: list[dict[str, Any]]) -> None:
    client.hset(_job_key(job_id), mapping={"files": json.dumps(files)})


def sync_is_cancelled(client: sync_redis.Redis, job_id: str) -> bool:
    return bool(client.exists(_cancel_key(job_id)))


def sync_is_paused(client: sync_redis.Redis, job_id: str) -> bool:
    return bool(client.exists(_pause_key(job_id)))


# -- async (used by the FastAPI process) -------------------------------------
def async_client() -> async_redis.Redis:
    return async_redis.Redis.from_url(REDIS_URL, decode_responses=True)


async def create_job_record(
    client: async_redis.Redis, job_id: str, *, owner_id: str, title: str, kind: str, total: int
) -> None:
    now = time.time()
    await client.hset(
        _job_key(job_id),
        mapping={
            "job_id": job_id,
            "owner_id": owner_id,
            "state": "queued",
            "title": title,
            "kind": kind,
            "percent": "0",
            "status": "Queued",
            "speed": "",
            "eta": "",
            "done": "0",
            "total": str(total),
            "error": "",
            "created_at": str(now),
        },
    )
    await client.zadd("jobs:index", {job_id: now})


async def get_job(client: async_redis.Redis, job_id: str) -> dict[str, Any] | None:
    data = await client.hgetall(_job_key(job_id))
    return data or None


async def list_jobs(client: async_redis.Redis, *, owner_id: str, limit: int = 200) -> list[dict[str, Any]]:
    ids = await client.zrevrange("jobs:index", 0, limit - 1)
    if not ids:
        return []
    pipe = client.pipeline()
    for job_id in ids:
        pipe.hgetall(_job_key(job_id))
    results = await pipe.execute()
    return [r for r in results if r and r.get("owner_id") == owner_id]


async def get_job_files(client: async_redis.Redis, job_id: str) -> list[dict[str, Any]]:
    raw = await client.hget(_job_key(job_id), "files")
    return json.loads(raw) if raw else []


async def request_cancel(client: async_redis.Redis, job_id: str) -> None:
    await client.set(_cancel_key(job_id), "1", ex=_CANCEL_TTL_SECONDS)


async def request_pause(client: async_redis.Redis, job_id: str) -> None:
    await client.set(_pause_key(job_id), "1", ex=_PAUSE_TTL_SECONDS)


async def request_resume(client: async_redis.Redis, job_id: str) -> None:
    await client.delete(_pause_key(job_id))


def _flatten(event: dict[str, Any]) -> dict[str, str]:
    """Redis hashes are string->string; coerce and drop the routing-only 'type' key."""
    return {k: ("" if v is None else str(v)) for k, v in event.items() if k != "type"}


# -- subscriptions ------------------------------------------------------------
def _sub_key(sub_id: str) -> str:
    return f"sub:{sub_id}"


async def create_subscription(
    client: async_redis.Redis, sub_id: str, *, owner_id: str, url: str, title: str, kind: str, interval_minutes: int
) -> None:
    await client.hset(
        _sub_key(sub_id),
        mapping={
            "id": sub_id,
            "owner_id": owner_id,
            "url": url,
            "title": title,
            "kind": kind,
            "interval_minutes": str(interval_minutes),
            "last_checked": "0",
            "new_count": "0",
            "known_ids": "[]",
        },
    )
    await client.sadd("subs:index", sub_id)


async def get_subscription(client: async_redis.Redis, sub_id: str) -> Subscription | None:
    data = await client.hgetall(_sub_key(sub_id))
    return _sub_from_hash(data) if data else None


async def list_subscriptions(client: async_redis.Redis, *, owner_id: str | None = None) -> list[Subscription]:
    """``owner_id=None`` returns every subscription — used by the cron sweep,
    which must check everyone's, not just one user's."""
    ids = await client.smembers("subs:index")
    if not ids:
        return []
    pipe = client.pipeline()
    for sub_id in ids:
        pipe.hgetall(_sub_key(sub_id))
    results = await pipe.execute()
    subs = [_sub_from_hash(r) for r in results if r]
    if owner_id is not None:
        subs = [s for s in subs if s.owner_id == owner_id]
    return subs


async def delete_subscription(client: async_redis.Redis, sub_id: str) -> None:
    await client.delete(_sub_key(sub_id))
    await client.srem("subs:index", sub_id)


async def save_subscription(client: async_redis.Redis, sub: Subscription) -> None:
    await client.hset(
        _sub_key(sub.id),
        mapping={
            "id": sub.id,
            "owner_id": sub.owner_id,
            "url": sub.url,
            "title": sub.title,
            "kind": sub.kind,
            "interval_minutes": str(sub.interval_minutes),
            "last_checked": str(sub.last_checked),
            "new_count": str(sub.new_count),
            "known_ids": json.dumps(sub.known_ids),
        },
    )


def _sub_from_hash(data: dict[str, str]) -> Subscription:
    return Subscription(
        id=data["id"],
        owner_id=data.get("owner_id", ""),
        url=data["url"],
        title=data.get("title", ""),
        kind=data.get("kind", "playlist"),
        interval_minutes=int(data.get("interval_minutes", 60)),
        last_checked=float(data.get("last_checked", 0)),
        new_count=int(data.get("new_count", 0)),
        known_ids=json.loads(data.get("known_ids") or "[]"),
    )
