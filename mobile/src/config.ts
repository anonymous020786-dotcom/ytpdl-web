import * as SecureStore from "expo-secure-store";

// Points at the same FastAPI backend the web frontend and Telegram bot use —
// this app adds no new server-side logic, just another client.
//
// Runtime-configurable rather than baked in at build time: a LAN IP for
// local dev testing changes on DHCP renewal, and rebuilding the app via EAS
// (~10 min) just to update it is exactly the kind of thing that should not
// need a rebuild. See SettingsScreen — the value here is only the *default*
// for a fresh install; getApiBaseUrl() checks SecureStore first.
//
// On a physical device/Expo Go, "localhost" means the phone itself, not your
// dev machine. The Android emulator's special alias for the host machine is
// 10.0.2.2, not localhost.
const DEFAULT_API_BASE_URL = process.env.EXPO_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

const API_BASE_URL_KEY = "ytpdl_api_base_url";

function normalize(url: string): string {
  return url.trim().replace(/\/+$/, "");
}

export async function getApiBaseUrl(): Promise<string> {
  const stored = await SecureStore.getItemAsync(API_BASE_URL_KEY);
  return normalize(stored || DEFAULT_API_BASE_URL);
}

export async function setApiBaseUrl(url: string): Promise<void> {
  await SecureStore.setItemAsync(API_BASE_URL_KEY, normalize(url));
}

export async function getWsBaseUrl(): Promise<string> {
  return (await getApiBaseUrl()).replace(/^http/, "ws");
}

export { DEFAULT_API_BASE_URL };
