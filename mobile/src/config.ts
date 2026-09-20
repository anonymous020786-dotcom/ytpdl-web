// Points at the same FastAPI backend the web frontend and Telegram bot use —
// this app adds no new server-side logic, just another client.
//
// On a physical device/Expo Go, "localhost" means the phone itself, not your
// dev machine — set EXPO_PUBLIC_API_BASE_URL to your machine's LAN IP (e.g.
// http://192.168.1.20:8000) when testing on a real device. The Android
// emulator's special alias for the host machine is 10.0.2.2, not localhost.
export const API_BASE_URL = process.env.EXPO_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export const WS_BASE_URL = API_BASE_URL.replace(/^http/, "ws");
