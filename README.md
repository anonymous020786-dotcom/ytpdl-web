# ytpdl-web

Web port of [yt-playlist-downloader-py](https://github.com/anonymous020786-dotcom/yt-playlist-downloader-py),
a PySide6 desktop app. The desktop app's `ytpdl/core/` package (resolver,
filename templating, tagging, title parsing) had no Qt dependency and is
copied here unchanged under `backend/app/core/`. `ytpdl/core/downloader.py`
and `ytpdl/core/queue.py` *did* depend on Qt (`QRunnable`, `QThreadPool`,
`Signal`) — those are reimplemented as `backend/app/jobs.py` (the same job
logic, callback-based instead of signal-based) and an arq/Redis task queue
(`backend/app/worker.py`) instead of a thread pool. The Qt UI itself
(`ytpdl/ui/`) has no web equivalent here — it's replaced by `frontend/`.

## Architecture

```
frontend/   React + TypeScript (Vite) — accounts, submit a link, watch jobs progress live
mobile/     React Native + Expo (iOS/Android) — same accounts/API, native app instead of a browser
backend/    FastAPI (app/main.py) — REST + WebSocket API, per-user accounts (app/auth.py + app/db.py)
            arq worker (app/worker.py) — runs one DownloadRunner per job, checks subscriptions on a cron
            Telegram bot (app/bot/) — same download engine, chat-based UI instead of a browser
            Redis — job queue + job/subscription state + pub/sub for live progress
            SQLite (dev) / Postgres (docker-compose) — user accounts (web app only)
Caddy       reverse proxy + static file server + auto-HTTPS (production only)
```

The bot and the mobile app are both second/third *frontends* onto the exact
same backend — the bot enqueues onto the same arq queue (`run_download_job`
in `worker.py`, unmodified) and listens to the same `job-events` Redis
channel the web app's WebSocket bridge uses; the mobile app calls the exact
same REST + WebSocket endpoints the web frontend does, with the same
email/password JWT accounts. A Telegram user's identity is just their chat
id (`owner_id = "tg:<chat_id>"`) — no separate login, same as any other
Telegram bot. See `backend/app/bot/README.md` and `mobile/README.md` for
client-specific setup.

Progress flow: a worker thread running yt-dlp calls a plain Python callback
on every hook → that publishes to a Redis channel (tagged with the owning
user's id) → the FastAPI process (subscribed to that channel) fans it out to
that user's connected WebSocket client(s) only. This is why jobs survive an
API process restart, why multiple tabs for the same account see the same
progress, and why users can't see each other's downloads.

Every job and subscription is owned by whoever created it — enforced on
every read (list/get/cancel/pause/resume/file-download), not just at
creation. See `backend/app/auth.py`, and `_get_owned_job`/
`_get_owned_subscription` in `backend/app/main.py`.

## Where files end up

Every finished download lands on the **server**, under
`DOWNLOAD_ROOT/<job_id>/...` — for local dev that's `./data/downloads/`
inside this repo (gitignored; set `DOWNLOAD_ROOT` to point elsewhere, e.g.
in `.env` for Docker). The browser only gets a copy when you click a
finished job's file in the UI:

- **Chrome/Edge**: clicking a file opens a native "Save As" dialog — you
  pick the exact folder on your own machine.
- **Firefox/Safari**: browsers don't let a web page open a save-location
  picker, so the file goes to your browser's configured Downloads folder
  instead (the most any website can do there).

The server copy under `data/downloads/` stays put after that — nothing
deletes it automatically yet (see the `JOB_TTL_HOURS` note in `config.py`;
it's currently metadata-only, not enforced by a cleanup job).

## Running locally (no Docker)

Backend:

```bash
cd backend
python -m venv .venv && .venv/Scripts/activate  # or source .venv/bin/activate
pip install -r requirements.txt
# needs a local Redis on 6379, and ffmpeg on PATH
set REDIS_URL=redis://localhost:6379/0
uvicorn app.main:app --reload --port 8000
```

No `DATABASE_URL` needed for local dev — it defaults to a SQLite file
(`backend/ytpdl.db`) created automatically on first startup.

Worker (separate terminal, same venv/env):

```bash
arq app.worker.WorkerSettings
```

Frontend (separate terminal):

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173 and sign up — `SIGNUP_INVITE_CODE` is unset by
default so registration is open, fine on localhost, never once this is
reachable from anywhere else.

## Running with Docker Compose

```bash
cp .env.example .env   # set real JWT_SECRET and POSTGRES_PASSWORD, and SIGNUP_INVITE_CODE
docker compose up --build
```

This brings up Postgres (accounts) + Redis (jobs/subscriptions/queue) instead
of SQLite. Caddy listens on :80/:443, serves the built frontend, and proxies
`/api` and `/ws` to the API container. Set `SITE_ADDRESS` in `.env` to a real
domain to get automatic HTTPS from Caddy; leave it as `localhost` for local
testing.

## Follow-ups not in this scaffold

- **Password reset / email verification**: registration only checks the
  email isn't already taken — there's no "confirm your email" or "forgot
  password" flow. Fine for a small trusted instance, not for public signup.
- **Long-lived JWTs, no revocation**: tokens are valid for `JWT_TTL_SECONDS`
  (30 days) with no server-side revocation list — logging out just deletes
  the token client-side. Add refresh tokens + a revocation/blacklist store if
  "log out everywhere" or shorter-lived sessions matter to you.
- **Job listing at scale**: `store.list_jobs` fetches the most recent
  `limit` jobs *across all users* from a single Redis zset, then filters to
  the caller — fine at scaffold scale, but a very active instance should
  move job history into Postgres with a per-user index (the README's
  original note about Redis being TTL'd/ephemeral by design still applies).
- **i18n**: the desktop app's 14 translated locales weren't ported to the
  frontend.
- **Storage**: files are written to a local Docker volume (`DOWNLOAD_ROOT`).
  For a public-facing deployment with real traffic, prefer S3-compatible
  object storage (Cloudflare R2 / Backblaze B2) with signed URLs and a
  TTL-based cleanup job, so the app server's disk doesn't fill up.
- **Rate limiting**: nothing throttles `/api/auth/register` or `/api/auth/login`
  — add rate limiting before those are internet-facing, or they're an easy
  brute-force/signup-spam target.
- **Legal**: YouTube's ToS prohibits downloading. `SIGNUP_INVITE_CODE` keeps
  this from becoming an open public downloader the moment it's reachable
  from the internet — set it (see `.env.example`) before deploying anywhere
  but a fully trusted private instance.
