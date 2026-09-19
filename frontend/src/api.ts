import type { AuthResponse, DownloadSettingsInput, JobFile, JobRecord, ResolvedSource, Subscription, User } from "./types";

const TOKEN_KEY = "ytpdl_token";

export function getToken(): string {
  return localStorage.getItem(TOKEN_KEY) ?? "";
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}),
      ...(init?.headers ?? {}),
    },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(body.detail ?? `${res.status} ${res.statusText}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  register: (email: string, password: string, inviteCode: string) =>
    request<AuthResponse>("/api/auth/register", {
      method: "POST",
      body: JSON.stringify({ email, password, invite_code: inviteCode }),
    }),

  login: (email: string, password: string) =>
    request<AuthResponse>("/api/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }),

  me: () => request<User>("/api/auth/me"),

  resolve: (url: string, cookiesFromBrowser = "") =>
    request<ResolvedSource>("/api/resolve", {
      method: "POST",
      body: JSON.stringify({ url, cookies_from_browser: cookiesFromBrowser }),
    }),

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

  fileUrl: (jobId: string, name: string) =>
    `/api/jobs/${jobId}/files/${encodeURIComponent(name)}?token=${encodeURIComponent(getToken())}`,

  wsUrl: () => {
    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    const q = getToken() ? `?token=${encodeURIComponent(getToken())}` : "";
    return `${proto}//${location.host}/ws${q}`;
  },
};
