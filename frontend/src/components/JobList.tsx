import { JobRow } from "./JobRow";
import type { JobRecord } from "../types";

interface JobListProps {
  jobs: JobRecord[];
  onCancel: (jobId: string) => void;
  onPause: (jobId: string) => void;
  onResume: (jobId: string) => void;
}

export function JobList({ jobs, onCancel, onPause, onResume }: JobListProps) {
  if (jobs.length === 0) {
    return <p className="muted">No jobs yet — paste a link above to get started.</p>;
  }
  return (
    <div className="job-list">
      {jobs.map((job) => (
        <JobRow key={job.job_id} job={job} onCancel={onCancel} onPause={onPause} onResume={onResume} />
      ))}
    </div>
  );
}
