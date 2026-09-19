import { useEffect, useState } from "react";
import { api } from "../api";
import type { Subscription } from "../types";

function timeAgo(unixSeconds: number): string {
  if (!unixSeconds) return "never";
  const seconds = Math.max(0, Date.now() / 1000 - unixSeconds);
  if (seconds < 90) return "just now";
  const minutes = Math.round(seconds / 60);
  if (minutes < 90) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  return `${hours}h ago`;
}

export function Subscriptions() {
  const [subs, setSubs] = useState<Subscription[]>([]);
  const [url, setUrl] = useState("");
  const [interval, setIntervalMinutes] = useState(60);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const refresh = () => api.listSubscriptions().then(setSubs).catch(() => {});

  useEffect(() => {
    refresh();
    const poll = setInterval(refresh, 20000);
    return () => clearInterval(poll);
  }, []);

  async function handleAdd(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api.createSubscription(url, interval);
      setUrl("");
      refresh();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function handleCheck(subId: string) {
    await api.checkSubscription(subId);
  }

  async function handleDelete(subId: string) {
    await api.deleteSubscription(subId);
    refresh();
  }

  return (
    <div className="card">
      <form onSubmit={handleAdd} className="row">
        <input
          type="text"
          placeholder="Channel or playlist link to watch for new uploads"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          required
        />
        <select value={interval} onChange={(e) => setIntervalMinutes(Number(e.target.value))}>
          <option value={15}>every 15 min</option>
          <option value={30}>every 30 min</option>
          <option value={60}>every hour</option>
          <option value={360}>every 6 hours</option>
          <option value={1440}>daily</option>
        </select>
        <button type="submit" disabled={busy}>
          {busy ? "Adding…" : "Subscribe"}
        </button>
      </form>
      {error && <p className="error">{error}</p>}

      {subs.length === 0 ? (
        <p className="muted">No subscriptions — new uploads from a channel or playlist get auto-queued once you add one.</p>
      ) : (
        <ul className="sub-list">
          {subs.map((s) => (
            <li key={s.id} className="sub-row">
              <div>
                <strong>{s.title || s.url}</strong>
                <div className="muted small">
                  {s.kind} · every {s.interval_minutes}m · checked {timeAgo(s.last_checked)} · {s.known_ids.length} known
                </div>
              </div>
              <div className="job-actions">
                <button className="link-btn" onClick={() => handleCheck(s.id)}>
                  Check now
                </button>
                <button className="link-btn" onClick={() => handleDelete(s.id)}>
                  Remove
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
