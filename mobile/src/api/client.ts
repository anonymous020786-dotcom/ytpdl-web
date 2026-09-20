import * as SecureStore from "expo-secure-store";

import { getApiBaseUrl } from "../config";
import type {
  AuthResponse,
  DownloadSettingsInput,
  JobFile,
  JobRecord,
  ResolvedSource,
  Subscription,
  User,
} from "./types";

const TOKEN_KEY = "ytpdl_token";

// SecureStore (Keychain on iOS, Keystore on Android) instead of localStorage
// — there's no browser storage on a phone, and this is the appropriate place
// for a bearer token on-device.
export async function getToken(): Promise<string | null> {
  return SecureStore.getItemAsync(TOKEN_KEY);
}

export async function setToken(token: string): Promise<void> {
  await SecureStore.setItemAsync(TOKEN_KEY, token);
}

export async function clearToken(): Promise<void> {
  await SecureStore.deleteItemAsync(TOKEN_KEY);
}

class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const [token, baseUrl] = await Promise.all([getToken(), getApiBaseUrl()]);
  const res = await fetch(`${baseUrl}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(init?.headers ?? {}),
    },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new ApiError(body.detail ?? `${res.status} ${res.statusText}`, res.status);
  }
  return res.json() as Promise<T>;
}

export { ApiError };

export const api = {
  register: (email: string, password: string, inviteCode: string) =>
    request<AuthResponse>("/api/auth/register", {
      method: "POST",
      body: JSON.stringify({ email, password, invite_code: inviteCode }),
    }),

  login: (email: string, password: string) =>
    request<AuthResponse>("/api/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }),

  me: () => request<User>("/api/auth/me"),

  resolve: (url: string) =>
    request<ResolvedSource>("/api/resolve", { method: "POST", body: JSON.stringify({ url }) }),

  createJob: (source: ResolvedSource, settings: DownloadSettingsInput) =>
    request<{ job_id: string }>("/api/jobs", {
      method: "POST",
      body: JSON.stringify({ source, settings }),
    }),

  listJobs: () => request<JobRecord[]>("/api/jobs"),

  cancelJob: (jobId: string) => request<{ ok: boolean }>(`/api/jobs/${jobId}/cancel`, { method: "POST" }),
  pauseJob: (jobId: string) => request<{ ok: boolean }>(`/api/jobs/${jobId}/pause`, { method: "POST" }),
  resumeJob: (jobId: string) => request<{ ok: boolean }>(`/api/jobs/${jobId}/resume`, { method: "POST" }),

  jobFiles: (jobId: string) => request<JobFile[]>(`/api/jobs/${jobId}/files`),

  fileUrl: async (jobId: string, name: string) => {
    const [token, baseUrl] = await Promise.all([getToken(), getApiBaseUrl()]);
    return `${baseUrl}/api/jobs/${jobId}/files/${encodeURIComponent(name)}?token=${encodeURIComponent(token ?? "")}`;
  },

  listSubscriptions: () => request<Subscription[]>("/api/subscriptions"),

  createSubscription: (url: string, intervalMinutes: number) =>
    request<Subscription>("/api/subscriptions", {
      method: "POST",
      body: JSON.stringify({ url, interval_minutes: intervalMinutes }),
    }),

  deleteSubscription: (subId: string) =>
    request<{ ok: boolean }>(`/api/subscriptions/${subId}`, { method: "DELETE" }),

  checkSubscription: (subId: string) =>
    request<{ ok: boolean; queued: boolean }>(`/api/subscriptions/${subId}/check`, { method: "POST" }),
};
