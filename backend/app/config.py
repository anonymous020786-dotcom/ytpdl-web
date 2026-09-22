"""Server-wide configuration, read from the environment.

Everything here has a sane container default so ``docker compose up`` works
out of the box; override via ``.env`` / compose ``environment:`` for anything
that needs to differ in production (see ``.env.example`` at the repo root).
"""

from __future__ import annotations

import os
from pathlib import Path

REDIS_URL: str = os.environ.get("REDIS_URL", "redis://redis:6379/0")

# Where finished downloads land. Mount this as a volume so files survive
# container restarts and can be served back to clients.
DOWNLOAD_ROOT: Path = Path(os.environ.get("DOWNLOAD_ROOT", "/data/downloads"))

# Scratch space for in-progress yt-dlp runs; wiped per job on completion.
WORK_ROOT: Path = Path(os.environ.get("WORK_ROOT", "/data/work"))

# Signs JWTs issued at login. The fallback is fine on localhost only — set a
# real random value (e.g. `python -c "import secrets; print(secrets.token_hex(32))"`)
# before this is reachable from anywhere else, or anyone can forge a token.
JWT_SECRET: str = os.environ.get("JWT_SECRET", "dev-insecure-secret-change-me")
JWT_TTL_SECONDS: int = int(os.environ.get("JWT_TTL_SECONDS", str(30 * 24 * 3600)))  # 30 days

# If set, registering an account requires this code (a simple door lock, not
# per-user permissions). Leave unset only for local dev / a fully trusted
# private instance — with it blank, anyone who reaches /api/auth/register can
# create an account and start spending your VPS's disk and bandwidth on
# downloads (and YouTube's ToS prohibits that use in general).
SIGNUP_INVITE_CODE: str = os.environ.get("SIGNUP_INVITE_CODE", "")

# Server-side ceiling regardless of what a client requests; keeps one job
# from starving the box. Matches the desktop app's "concurrent downloads"
# app setting, but here it's an arq worker pool size (see worker.py).
MAX_CONCURRENT_DOWNLOADS: int = int(os.environ.get("MAX_CONCURRENT_DOWNLOADS", "2"))

RATE_LIMIT_KIB: int = int(os.environ.get("RATE_LIMIT_KIB", "0"))  # 0 == unlimited
COOKIES_FROM_BROWSER: str = os.environ.get("COOKIES_FROM_BROWSER", "")

# How long a finished/failed job's Redis record + files are kept before a
# caller should consider them gone. Enforced by a periodic arq cron job
# (see worker.py); this is metadata only, it doesn't delete anything itself.
JOB_TTL_HOURS: int = int(os.environ.get("JOB_TTL_HOURS", "48"))

# Default "check for new uploads" cadence for a subscription that doesn't
# specify its own. The cron task in worker.py runs every minute and skips
# any subscription whose own interval hasn't elapsed yet.
DEFAULT_SUBSCRIPTION_INTERVAL_MINUTES: int = int(os.environ.get("DEFAULT_SUBSCRIPTION_INTERVAL_MINUTES", "60"))

# -- Serverless (AWS Lambda) deployment -----------------------------------------
# Set automatically by the Lambda runtime; used to switch off arq/WebSocket
# machinery that doesn't fit a stateless, per-invocation environment.
IS_LAMBDA: bool = bool(os.environ.get("AWS_LAMBDA_FUNCTION_NAME", ""))

# When set, finished job files are uploaded to this S3 bucket instead of
# staying on local disk (Lambda's /tmp isn't shared across functions or
# invocations), and served back to clients via presigned URLs.
S3_BUCKET: str = os.environ.get("S3_BUCKET", "")
AWS_REGION: str = os.environ.get("AWS_REGION", "ap-south-1")

# Name of the separate Lambda function that actually runs yt-dlp/ffmpeg
# (the API Lambda stays thin and fast; this one gets a long timeout).
# Invoked asynchronously in place of arq's ``enqueue_job``.
WORKER_LAMBDA_NAME: str = os.environ.get("WORKER_LAMBDA_NAME", "")

# Base URL of a bgutil-ytdlp-pot-provider instance (see
# https://github.com/Brainicism/bgutil-ytdlp-pot-provider). YouTube
# aggressively fingerprints and blocks requests from datacenter IP ranges
# (AWS/GCP/Azure/Cloudflare all included) with "Sign in to confirm you're
# not a bot" — this mints PO tokens that make yt-dlp's requests look
# legitimate even from Lambda. Leave unset to run without it (fine on a
# residential IP, will hit the bot check from Lambda).
POT_PROVIDER_BASE_URL: str = os.environ.get("POT_PROVIDER_BASE_URL", "")


def pot_extractor_args() -> dict:
    """Anti-bot-detection opts for yt-dlp, needed when running from a
    datacenter IP (AWS/GCP/Azure/any VPS — YouTube blocks these regardless
    of provider): a PO token from the bgutil sidecar, plus quickjs as the JS
    challenge-solver runtime (deno also works but its binary is ~96MB vs
    quickjs's ~2MB, which matters for the Lambda layer size budget) and
    permission to fetch the (small, cached) challenge-solver script.
    Verified end-to-end against real YouTube videos with this exact
    combination — no JS runtime, or player clients that skip PO tokens
    entirely (e.g. mweb), were NOT sufficient on their own.
    """
    if not POT_PROVIDER_BASE_URL:
        return {}
    return {
        "extractor_args": {"youtubepot-bgutilhttp": {"base_url": [POT_PROVIDER_BASE_URL]}},
        "js_runtimes": {"quickjs": {}},
        "remote_components": ["ejs:github"],
    }


def ensure_dirs() -> None:
    DOWNLOAD_ROOT.mkdir(parents=True, exist_ok=True)
    WORK_ROOT.mkdir(parents=True, exist_ok=True)


# Comma-separated list of origins allowed to call the API (CORS). Defaults to
# "*" for zero-friction local dev; set this to your real frontend origin(s)
# (e.g. "https://ytpdl.example.com") once this is deployed, since JWTs are
# bearer tokens a malicious origin could otherwise try to use from a
# victim's browser if it got hold of one.
_raw_origins = os.environ.get("CORS_ORIGINS", "*")
ALLOWED_ORIGINS: list[str] = [o.strip() for o in _raw_origins.split(",") if o.strip()]

# -- Telegram bot (backend/app/bot/) -------------------------------------------
TELEGRAM_BOT_TOKEN: str = os.environ.get("TELEGRAM_BOT_TOKEN", "")

# Checked against Telegram's X-Telegram-Bot-Api-Secret-Token header on every
# webhook call (Lambda deployment only — see app/bot_lambda_handler.py) so a
# stranger who finds the webhook URL can't feed it fake updates.
TELEGRAM_WEBHOOK_SECRET: str = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "")

# Point this at a self-hosted Local Bot API Server (https://github.com/tdlib/telegram-bot-api)
# to lift the standard 50MB file-send limit to 2GB and send files straight off
# disk with no re-upload. Leave unset to use Telegram's regular cloud Bot API
# (works anywhere, no extra infra, but finished videos over 50MB can't be sent
# in-chat — the bot tells the user instead of silently failing).
TELEGRAM_LOCAL_API_URL: str = os.environ.get("TELEGRAM_LOCAL_API_URL", "")

# Only meaningful together with TELEGRAM_LOCAL_API_URL: the bot and the local
# server share DOWNLOAD_ROOT on disk, so files are handed over by path
# (file://...) instead of being read into memory and re-uploaded.
TELEGRAM_LOCAL_MODE: bool = bool(TELEGRAM_LOCAL_API_URL)

# Hard cap on how much of a chat's history the "cloud" (non-local) API will
# upload in one go before telling the user to enable the local server instead.
TELEGRAM_CLOUD_FILE_LIMIT_MB: int = 50

# python-telegram-bot's default upload timeout (media_write_timeout) is only
# 20s — fine for a small icon, nowhere near enough for a video on a slow or
# congested link (observed as low as ~75 KB/s in testing, where even a 10MB
# file needs over 130s). A VPS's path to Telegram's datacenters should be far
# faster than a home connection, but the cost of setting this too low is a
# silent-looking TimedOut on an upload that was actually still in progress,
# so the default here is deliberately generous.
TELEGRAM_UPLOAD_TIMEOUT_SECONDS: int = int(os.environ.get("TELEGRAM_UPLOAD_TIMEOUT_SECONDS", "600"))
