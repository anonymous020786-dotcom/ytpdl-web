// Mirrors backend/app/main.py's response shapes and
// backend/app/core/models.py / settings.py — same contract the web
// frontend (frontend/src/types.ts) uses, since it's the same backend.

export interface VideoInfo {
  id: string;
  title: string;
  url: string;
  author: string;
  duration: number | null;
  thumbnail: string;
}

export type SourceKind = "video" | "playlist" | "channel";

export interface ResolvedSource {
  kind: SourceKind;
  title: string;
  url: string;
  author: string;
  thumbnail: string;
  videos: VideoInfo[];
}

export interface DownloadSettingsInput {
  audio_only: boolean;
  audio_format: string;
  video_format: string;
  quality: string;
  convert: boolean;
  embed_thumbnail: boolean;
  tag_audio: boolean;
  separate_playlist_folders: boolean;
  filename_template: string;
}

export type JobState = "queued" | "running" | "paused" | "completed" | "failed" | "cancelled";

export interface JobRecord {
  job_id: string;
  state: JobState;
  title: string;
  kind: SourceKind;
  percent: string;
  status: string;
  speed: string;
  eta: string;
  done: string;
  total: string;
  error: string;
  created_at: string;
}

export interface JobFile {
  name: string;
  size: number;
}

export interface Subscription {
  id: string;
  url: string;
  title: string;
  kind: SourceKind;
  interval_minutes: number;
  last_checked: number;
  new_count: number;
  known_ids: string[];
}

export interface User {
  id: string;
  email: string;
}

export interface AuthResponse {
  token: string;
  user: User;
}
