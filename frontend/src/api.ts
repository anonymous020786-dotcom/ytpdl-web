import type { DownloadSettingsInput, JobFile, JobRecord, ResolvedSource, Subscription } from "./types";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: {
      "Content-Type": "application/json",
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
    `/api/jobs/${jobId}/files/${encodeURIComponent(name)}`,

  wsUrl: () => {
    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    return `${proto}//${location.host}/ws`;
  },
};
