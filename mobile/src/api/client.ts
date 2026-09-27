import { getApiBaseUrl } from "../config";
import type {
  DownloadSettingsInput,
  JobFile,
  JobRecord,
  ResolvedSource,
  Subscription,
} from "./types";

class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const baseUrl = await getApiBaseUrl();
  const res = await fetch(`${baseUrl}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
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
    const baseUrl = await getApiBaseUrl();
    return `${baseUrl}/api/jobs/${jobId}/files/${encodeURIComponent(name)}`;
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
