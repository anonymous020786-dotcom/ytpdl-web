# Telegram bot

Same download engine as the web app (`../core/`, `../jobs.py`, `../worker.py`
— all unchanged), different frontend. No account/login: a Telegram user is
identified purely by their chat id (`owner_id = "tg:<chat_id>"`).

## What it does

- Paste a link (video/playlist/channel) → pick audio-only or video →
  pick format/quality → downloads, editing one message with a live progress
  bar, speed, and ETA as it goes.
- Inline **Pause / Resume / Cancel** buttons on the progress message.
- On completion, sends the finished file(s) straight into the chat.
- `/subscribe <link> [interval-minutes]` — new uploads on a channel/playlist
  get downloaded and sent to you automatically, no further action needed.
- `/subscriptions`, `/jobs` — manage subscriptions, see recent downloads.
- DMs only (group chats are ignored) — this is a personal downloader per
  Telegram account, not a shared bot in a group.

## Getting a bot token

Message **@BotFather** on Telegram → `/newbot` → follow the prompts. You get
back a token that looks like `123456789:AAH...`. Set it as `TELEGRAM_BOT_TOKEN`.

## File size: cloud API vs. Local Bot API Server

Telegram's standard (cloud) Bot API caps files sent *to* a chat at **50MB**.
Most full-length videos exceed that. Two ways to handle it:

1. **Do nothing** (default). Files over 50MB get a message explaining why
   they weren't sent instead of a silent failure. Audio-only downloads are
   almost always under the cap, so this is fine for an audio-focused bot.
2. **Run a [Local Bot API Server](https://github.com/tdlib/telegram-bot-api)**
   (`docker-compose.yml`'s `telegram-bot-api` service does this for you) —
   raises the limit to 2GB and, in local mode, hands Telegram a file path
   instead of re-uploading bytes over HTTP, since the server reads straight
   off the same disk. This needs a **second, different credential pair**:
   `TELEGRAM_API_ID` and `TELEGRAM_API_HASH` from
   **https://my.telegram.org/apps** — not from @BotFather. These authenticate
   the server process itself (tied to your personal Telegram account) and
   have nothing to do with the bot token.

Set `TELEGRAM_LOCAL_API_URL` (docker-compose does this automatically) to
switch the bot into local mode.

## Running locally (no Docker)

Same Redis/venv as the API and worker (see the repo root README). Then, in
a separate terminal:

```bash
cd backend
set TELEGRAM_BOT_TOKEN=123456789:your-token-from-botfather
python -m app.bot.main
```

No `TELEGRAM_LOCAL_API_URL` needed for local testing — it'll use the cloud
API (50MB cap). The web API and worker don't need to be running for the bot
itself to start, but the **worker** does need to be running for anything
you queue to actually download (the bot only enqueues jobs; `worker.py`
does the downloading, same as for web users).

## Running with Docker Compose

Already wired into the root `docker-compose.yml` — set `TELEGRAM_BOT_TOKEN`,
`TELEGRAM_API_ID`, and `TELEGRAM_API_HASH` in `.env` and `docker compose up`
starts both the bot and its Local Bot API Server alongside everything else.
