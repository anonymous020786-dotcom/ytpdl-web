import { useCallback, useEffect, useState } from "react";
import { api } from "./api";
import { SubmitForm } from "./components/SubmitForm";
import { JobList } from "./components/JobList";
import { Subscriptions } from "./components/Subscriptions";
import type { JobRecord } from "./types";

export default function App() {
  const [jobs, setJobs] = useState<JobRecord[]>([]);

  const refresh = useCallback(() => {
    api.listJobs().then(setJobs).catch(() => {});
  }, []);

  useEffect(() => {
    refresh();

    const ws = new WebSocket(api.wsUrl());
    ws.onmessage = (ev) => {
      const event = JSON.parse(ev.data);
      setJobs((prev) => {
        const idx = prev.findIndex((j) => j.job_id === event.job_id);
        if (idx === -1) return prev; // unknown job (created before this page loaded) — next poll picks it up
        const updated = { ...prev[idx] };
        for (const [key, value] of Object.entries(event)) {
          if (key === "job_id" || key === "type") continue;
          (updated as Record<string, string>)[key] = String(value);
        }
        const next = [...prev];
        next[idx] = updated;
        return next;
      });
    };

    const poll = setInterval(refresh, 15000); // safety net if the socket drops
    return () => {
      ws.close();
      clearInterval(poll);
    };
  }, [refresh]);

  async function handleCancel(jobId: string) {
    await api.cancelJob(jobId);
  }

  async function handlePause(jobId: string) {
    await api.pauseJob(jobId);
  }

  async function handleResume(jobId: string) {
    await api.resumeJob(jobId);
  }

  return (
    <div className="app">
      <header>
        <h1>YT Playlist Downloader</h1>
      </header>
      <SubmitForm onQueued={refresh} />
      <section>
        <h2>Jobs</h2>
        <JobList jobs={jobs} onCancel={handleCancel} onPause={handlePause} onResume={handleResume} />
      </section>
      <section>
        <h2>Subscriptions</h2>
        <Subscriptions />
      </section>
    </div>
  );
}
