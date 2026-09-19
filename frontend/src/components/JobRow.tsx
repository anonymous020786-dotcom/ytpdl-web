import { useEffect, useState } from "react";
import { api } from "../api";
import type { JobFile, JobRecord } from "../types";

const ACTIVE_STATES = new Set(["queued", "running", "paused"]);

interface JobRowProps {
  job: JobRecord;
  onCancel: (jobId: string) => void;
  onPause: (jobId: string) => void;
  onResume: (jobId: string) => void;
}

export function JobRow({ job, onCancel, onPause, onResume }: JobRowProps) {
  const [files, setFiles] = useState<JobFile[]>([]);

  useEffect(() => {
    if (job.state === "completed") {
      api.jobFiles(job.job_id).then(setFiles).catch(() => {});
    }
  }, [job.state, job.job_id]);

  const percent = Number(job.percent || 0);

  return (
    <div className="job-row">
      <div className="job-head">
        <strong>{job.title || job.job_id}</strong>
        <span className={`badge badge-${job.state}`}>{job.state}</span>
      </div>
      <div className="progress-bar">
        <div className="progress-fill" style={{ width: `${Math.min(100, percent)}%` }} />
      </div>
      <div className="job-meta">
        <span>{job.status}</span>
        {job.speed && <span>{job.speed}</span>}
        {job.eta && <span>ETA {job.eta}</span>}
        <span>
          {job.done}/{job.total}
        </span>
      </div>
      {job.error && <p className="error">{job.error}</p>}
      {ACTIVE_STATES.has(job.state) && (
        <div className="job-actions">
          {job.state === "running" && (
            <button className="link-btn" onClick={() => onPause(job.job_id)}>
              Pause
            </button>
          )}
          {job.state === "paused" && (
            <button className="link-btn" onClick={() => onResume(job.job_id)}>
              Resume
            </button>
          )}
          <button className="link-btn" onClick={() => onCancel(job.job_id)}>
            Cancel
          </button>
        </div>
      )}
      {files.length > 0 && (
        <ul className="file-list">
          {files.map((f) => (
            <li key={f.name}>
              <a href={api.fileUrl(job.job_id, f.name)} download={f.name}>
                {f.name}
              </a>{" "}
              <span className="muted">({(f.size / 1_048_576).toFixed(1)} MiB)</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
