"""FastAPI app: link resolution, download jobs on arq/Redis, subscriptions,
and live progress fanned out to WebSocket clients.

There are no accounts: every job and subscription created through this API
(web frontend or mobile app) belongs to the single ``WEB_OWNER_ID``. The
Telegram bot keeps its own per-chat ``tg:<chat_id>`` owners, so bot jobs
don't show up in the web UI and vice versa.
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import logging
import time
import uuid
from typing import Any

from arq import create_pool
from arq.connections import RedisSettings
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse, Response
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from . import store
from .config import (
    ALLOWED_ORIGINS,
    AWS_REGION,
    DEFAULT_SUBSCRIPTION_INTERVAL_MINUTES,
    DOWNLOAD_ROOT,
    EDGE_SECRET,
    IS_LAMBDA,
    REDIS_URL,
    S3_BUCKET,
    WORKER_LAMBDA_NAME,
    ensure_dirs,
    pot_extractor_args,
)
from .core import resolver
from .core.settings import DownloadSettings
from .core.subscriptions import Subscription

log = logging.getLogger("ytpdl.api")

# Owner id for everything created via this API — see module docstring.
WEB_OWNER_ID = "web"

app = FastAPI(title="YT Playlist Downloader API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,  # "*" by default; set CORS_ORIGINS in production, see config.py
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def _require_edge_secret(request, call_next):
    # 404, not 403 — a prober hitting the raw API Gateway/Function URL
    # directly sees "nothing here" rather than confirmation this is a
    # gated backend. Only the Cloudflare Worker knows EDGE_SECRET.
    if IS_LAMBDA and EDGE_SECRET and request.headers.get("x-edge-secret") != EDGE_SECRET:
        from fastapi.responses import Response

        return Response(status_code=404)
    return await call_next(request)


# -- websocket fan-out, scoped per owner ---------------------------------------
class ConnectionManager:
    def __init__(self) -> None:
        self._sockets: dict[WebSocket, str] = {}  # ws -> owner_id

    async def connect(self, ws: WebSocket, owner_id: str) -> None:
        await ws.accept()
        self._sockets[ws] = owner_id

    def disconnect(self, ws: WebSocket) -> None:
        self._sockets.pop(ws, None)

    async def broadcast_to_owner(self, owner_id: str, message: str) -> None:
        dead = []
        for ws, uid in self._sockets.items():
            if uid != owner_id:
                continue
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._sockets.pop(ws, None)


manager = ConnectionManager()


async def _pubsub_bridge() -> None:
    """Subscribe to Redis job-events and forward each message to the owning
    owner's WebSocket connection(s) only."""
    client = store.async_client()
    pubsub = client.pubsub()
    await pubsub.subscribe(store.EVENTS_CHANNEL)
    try:
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue
            owner_id = json.loads(message["data"]).get("owner_id")
            if owner_id:
                await manager.broadcast_to_owner(owner_id, message["data"])
    finally:
        await pubsub.unsubscribe(store.EVENTS_CHANNEL)
        await client.close()


@app.on_event("startup")
async def on_startup() -> None:
    ensure_dirs()
    app.state.redis = store.async_client()
    if IS_LAMBDA:
        # No persistent worker to enqueue to (see _invoke_worker_lambda) and
        # no long-lived connection for a WebSocket fan-out task to live on
        # between invocations — clients poll instead (see mobile/web README).
        app.state.arq_pool = None
    else:
        app.state.arq_pool = await create_pool(RedisSettings.from_dsn(REDIS_URL))
        app.state.bridge_task = asyncio.create_task(_pubsub_bridge())


@app.on_event("shutdown")
async def on_shutdown() -> None:
    if not IS_LAMBDA:
        app.state.bridge_task.cancel()
        await app.state.arq_pool.close()
    await app.state.redis.close()


def _invoke_worker_lambda(action: str, payload: dict) -> None:
    import json as _json

    import boto3

    client = boto3.client("lambda", region_name=AWS_REGION)
    client.invoke(
        FunctionName=WORKER_LAMBDA_NAME,
        InvocationType="Event",  # async/fire-and-forget — the API Lambda must not block on a download
        Payload=_json.dumps({"action": action, **payload}).encode(),
    )


# -- schemas --------------------------------------------------------------------
class ResolveRequest(BaseModel):
    url: str
    cookies_from_browser: str = ""


class JobCreateRequest(BaseModel):
    source: dict[str, Any]
    settings: dict[str, Any] = {}


class SubscriptionCreateRequest(BaseModel):
    url: str
    interval_minutes: int = DEFAULT_SUBSCRIPTION_INTERVAL_MINUTES


# -- health ---------------------------------------------------------------------
@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok"}


# -- resolve / jobs ---------------------------------------------------------
@app.post("/api/resolve")
async def api_resolve(body: ResolveRequest) -> dict:
    try:
        source = await run_in_threadpool(
            resolver.resolve,
            body.url,
            cookies_from_browser=body.cookies_from_browser,
            extra_opts=pot_extractor_args(),
        )
    except resolver.ResolveError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return source.to_dict()


@app.post("/api/jobs")
async def api_create_job(body: JobCreateRequest) -> dict:
    if not body.source.get("videos"):
        raise HTTPException(status_code=422, detail="source has no videos — resolve it first")

    settings = DownloadSettings.from_dict(body.settings)
    job_id = uuid.uuid4().hex[:12]

    await store.create_job_record(
        app.state.redis,
        job_id,
        owner_id=WEB_OWNER_ID,
        title=body.source.get("title", ""),
        kind=body.source.get("kind", "video"),
        total=len(body.source.get("videos", [])),
    )
    if IS_LAMBDA:
        await run_in_threadpool(
            _invoke_worker_lambda,
            "run_download_job",
            {"job_id": job_id, "source": body.source, "settings": settings.to_dict(), "owner_id": WEB_OWNER_ID},
        )
    else:
        await app.state.arq_pool.enqueue_job(
            "run_download_job", job_id, body.source, settings.to_dict(), WEB_OWNER_ID, _job_id=job_id
        )
    return {"job_id": job_id}


@app.get("/api/jobs")
async def api_list_jobs() -> list[dict]:
    return await store.list_jobs(app.state.redis, owner_id=WEB_OWNER_ID)


async def _get_owned_job(job_id: str) -> dict:
    job = await store.get_job(app.state.redis, job_id)
    if job is None or job.get("owner_id") != WEB_OWNER_ID:
        raise HTTPException(status_code=404, detail="job not found")
    return job


@app.get("/api/jobs/{job_id}")
async def api_get_job(job_id: str) -> dict:
    return await _get_owned_job(job_id)


@app.post("/api/jobs/{job_id}/cancel")
async def api_cancel_job(job_id: str) -> dict:
    await _get_owned_job(job_id)
    await store.request_cancel(app.state.redis, job_id)
    return {"ok": True}


@app.post("/api/jobs/{job_id}/pause")
async def api_pause_job(job_id: str) -> dict:
    job = await _get_owned_job(job_id)
    if job.get("state") != "running":
        raise HTTPException(status_code=409, detail=f"job is {job.get('state')}, not running")
    await store.request_pause(app.state.redis, job_id)
    return {"ok": True}


@app.post("/api/jobs/{job_id}/resume")
async def api_resume_job(job_id: str) -> dict:
    await _get_owned_job(job_id)
    await store.request_resume(app.state.redis, job_id)
    return {"ok": True}


@app.get("/api/jobs/{job_id}/files")
async def api_job_files(job_id: str) -> list[dict]:
    await _get_owned_job(job_id)
    if S3_BUCKET:
        files = await store.get_job_files(app.state.redis, job_id)
        return [{"name": f["name"], "size": f["size"]} for f in files]
    job_dir = DOWNLOAD_ROOT / job_id
    if not job_dir.is_dir():
        return []
    files = []
    for path in sorted(job_dir.rglob("*")):
        if path.is_file():
            rel = path.relative_to(job_dir)
            files.append({"name": str(rel), "size": path.stat().st_size})
    return files


@app.get("/api/jobs/{job_id}/files/{file_path:path}")
async def api_download_file(job_id: str, file_path: str) -> Response:
    await _get_owned_job(job_id)
    if S3_BUCKET:
        files = await store.get_job_files(app.state.redis, job_id)
        match = next((f for f in files if f["name"] == file_path), None)
        if match is None:
            raise HTTPException(status_code=404, detail="file not found")
        from . import storage

        url = await run_in_threadpool(storage.presigned_url, match["key"], file_path.rsplit("/", 1)[-1])
        return RedirectResponse(url)
    job_dir = (DOWNLOAD_ROOT / job_id).resolve()
    target = (job_dir / file_path).resolve()
    if job_dir not in target.parents or not target.is_file():
        raise HTTPException(status_code=404, detail="file not found")
    return FileResponse(target, filename=target.name)


# -- subscriptions ----------------------------------------------------------
@app.post("/api/subscriptions")
async def api_create_subscription(body: SubscriptionCreateRequest) -> dict:
    try:
        source = await run_in_threadpool(resolver.resolve, body.url, extra_opts=pot_extractor_args())
    except resolver.ResolveError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    sub_id = uuid.uuid4().hex[:12]
    ids = [v.id for v in source.videos if v.id]
    sub = Subscription(
        id=sub_id,
        owner_id=WEB_OWNER_ID,
        url=body.url,
        title=source.title,
        kind=source.kind.value,
        interval_minutes=body.interval_minutes,
        known_ids=ids[:500],
        last_checked=time.time(),
    )
    await store.create_subscription(
        app.state.redis, sub_id, owner_id=WEB_OWNER_ID, url=body.url, title=source.title,
        kind=source.kind.value, interval_minutes=body.interval_minutes,
    )
    await store.save_subscription(app.state.redis, sub)
    return dataclasses.asdict(sub)


@app.get("/api/subscriptions")
async def api_list_subscriptions() -> list[dict]:
    subs = await store.list_subscriptions(app.state.redis, owner_id=WEB_OWNER_ID)
    return [dataclasses.asdict(s) for s in subs]


async def _get_owned_subscription(sub_id: str) -> Subscription:
    sub = await store.get_subscription(app.state.redis, sub_id)
    if sub is None or sub.owner_id != WEB_OWNER_ID:
        raise HTTPException(status_code=404, detail="subscription not found")
    return sub


@app.delete("/api/subscriptions/{sub_id}")
async def api_delete_subscription(sub_id: str) -> dict:
    await _get_owned_subscription(sub_id)
    await store.delete_subscription(app.state.redis, sub_id)
    return {"ok": True}


@app.post("/api/subscriptions/{sub_id}/check")
async def api_check_subscription(sub_id: str) -> dict:
    await _get_owned_subscription(sub_id)
    if IS_LAMBDA:
        await run_in_threadpool(_invoke_worker_lambda, "check_one_subscription", {"sub_id": sub_id})
    else:
        await app.state.arq_pool.enqueue_job("check_one_subscription", sub_id)
    return {"ok": True, "queued": True}


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    await manager.connect(ws, WEB_OWNER_ID)
    try:
        while True:
            await ws.receive_text()  # client doesn't send anything meaningful; just keep the socket open
    except WebSocketDisconnect:
        manager.disconnect(ws)


# -- static frontend (Lambda deployment only) --------------------------------
# The docker-compose deployment serves the frontend from its own container
# behind Caddy; there's no separate static-hosting piece in the Lambda
# architecture, so the built frontend ships inside this same deployment
# package instead (see backend/app/static/, populated by the deploy script)
# and everything that isn't /api/* or /ws falls through to it here.
if IS_LAMBDA:
    from pathlib import Path

    from fastapi.responses import FileResponse as _FileResponse
    from fastapi.staticfiles import StaticFiles

    _STATIC_DIR = Path(__file__).parent / "static"
    if _STATIC_DIR.is_dir():
        app.mount("/assets", StaticFiles(directory=_STATIC_DIR / "assets"), name="frontend-assets")

        @app.get("/{full_path:path}")
        async def spa_fallback(full_path: str) -> _FileResponse:
            return _FileResponse(_STATIC_DIR / "index.html")
