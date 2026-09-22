"""Redis-backed state for the Telegram bot.

Two things live here:

* a per-chat "in progress link selection" scratch pad — paste a link, pick
  audio/video, pick quality/format, confirm — that survives a bot restart
  mid-flow (TTL'd, so an abandoned flow doesn't linger forever).
* job_id -> (chat_id, message_id), so progress.py knows which message to
  keep editing as a job's status changes, regardless of whether the job was
  started by a chat command or auto-queued by a subscription.
"""

from __future__ import annotations

import json

import redis as sync_redis
import redis.asyncio as async_redis

from ..config import REDIS_URL

_PENDING_TTL = 30 * 60  # abandon an unfinished link-selection flow after 30 min
_MSG_TTL = 48 * 3600


def client() -> async_redis.Redis:
    return async_redis.Redis.from_url(REDIS_URL, decode_responses=True)


def _pending_key(chat_id: int) -> str:
    return f"tgpending:{chat_id}"


async def save_pending(r: async_redis.Redis, chat_id: int, *, source: dict, settings: dict | None = None) -> None:
    payload = {"source": source, "settings": settings or {}}
    await r.set(_pending_key(chat_id), json.dumps(payload), ex=_PENDING_TTL)


async def load_pending(r: async_redis.Redis, chat_id: int) -> dict | None:
    raw = await r.get(_pending_key(chat_id))
    return json.loads(raw) if raw else None


async def clear_pending(r: async_redis.Redis, chat_id: int) -> None:
    await r.delete(_pending_key(chat_id))


def _msg_key(job_id: str) -> str:
    return f"tgmsg:{job_id}"


async def save_job_message(r: async_redis.Redis, job_id: str, *, chat_id: int, message_id: int) -> None:
    await r.hset(_msg_key(job_id), mapping={"chat_id": str(chat_id), "message_id": str(message_id)})
    await r.expire(_msg_key(job_id), _MSG_TTL)


async def get_job_message(r: async_redis.Redis, job_id: str) -> tuple[int, int] | None:
    data = await r.hgetall(_msg_key(job_id))
    if not data:
        return None
    return int(data["chat_id"]), int(data["message_id"])


# -- sync (used by worker.py, which runs in a plain thread, not an event loop) --
def sync_client() -> sync_redis.Redis:
    return sync_redis.Redis.from_url(REDIS_URL, decode_responses=True)


def sync_get_job_message(r: sync_redis.Redis, job_id: str) -> tuple[int, int] | None:
    data = r.hgetall(_msg_key(job_id))
    if not data:
        return None
    return int(data["chat_id"]), int(data["message_id"])
