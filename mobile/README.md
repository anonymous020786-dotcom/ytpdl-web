# ytpdl mobile

React Native + Expo app for iOS/Android. Same backend as `frontend/` (the
web app) and `backend/app/bot/` (the Telegram bot) — this adds no new
server-side logic, it's just another client against the existing FastAPI +
WebSocket API. Login/register, job resolution, queueing, live progress,
pause/resume/cancel, and subscriptions all hit the exact same endpoints the
web frontend uses (see `src/api/client.ts`).

## Running it for real, on your phone

```bash
cd mobile
npm install
npx expo start
```

Install **Expo Go** from the App Store / Play Store, then scan the QR code
`expo start` prints.

**Important**: on a physical phone, `localhost` means the phone itself, not
your dev machine. Set the API URL to your machine's LAN IP before starting:

```bash
# Windows: ipconfig | find "IPv4"    macOS/Linux: ifconfig | grep inet
EXPO_PUBLIC_API_BASE_URL=http://192.168.1.20:8000 npx expo start
```

Your phone and dev machine need to be on the same Wi-Fi network, and the
backend (`api` + `worker` + `redis`, see the repo root README) needs to
already be running and reachable at that address.

## What's built

- Email/password login & registration (same JWT auth as the web app),
  token stored in the device Keychain/Keystore via `expo-secure-store`
- Paste a link → resolve → pick audio/video + format/quality → queue
- Live job list: progress bar, speed/ETA, pause/resume/cancel — fed by the
  same `/ws` WebSocket the web frontend uses, with a 15s poll fallback
- Finished files: downloaded into the app's cache, then handed to the
  native share sheet (`expo-sharing`) — there's no universal "Downloads
  folder" API across iOS/Android for a third-party app, so "save to
  Files / share to another app" is the standard, App-Store-safe pattern
- Subscriptions: add/remove/check-now, same as the web app

## Verified

`npx tsc --noEmit` passes clean, and `npx expo export` bundles successfully
for both Android and iOS (859/864 modules, no errors) — proves every import
resolves and every native module is linked correctly. What I *can't* verify
from here: I don't have a physical device or emulator attached to this dev
environment, so the UI itself hasn't been visually tested — that needs you,
the same way live-testing the Telegram bot did.

## Not built yet

- **Push notifications**: `expo-notifications` isn't installed — recommending
  it and actually wiring it are different things. Doing it properly means:
  a device push-token registration endpoint on the backend, storing tokens
  per user, and the worker/progress-listener sending a push on job
  completion (mirroring how the bot proactively messages you). Real feature,
  not done — say the word and I'll build it.
- **App store distribution**: this runs today via Expo Go for development.
  Shipping a real installable build needs `eas build` (Expo's build service)
  — free for development/internal builds; publishing to the App Store needs
  an Apple Developer account ($99/yr), Play Store needs a one-time $25 fee.
- **Android release signing / iOS provisioning profiles**: not set up —
  only needed once you're ready for `eas build --profile production`.
