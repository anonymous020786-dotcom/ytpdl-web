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
