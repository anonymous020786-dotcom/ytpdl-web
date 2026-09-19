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

// Mirrors backend/app/core/settings.py::DownloadSettings (trimmed to the
// fields the UI actually exposes; the rest use their dataclass defaults).
export interface DownloadSettingsInput {
  audio_only: boolean;
  audio_format: string;
  video_format: string;
  quality: string;
  convert: boolean;
  download_subtitles: boolean;
  subtitle_languages: string;
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

export interface User {
  id: string;
  email: string;
}

export interface AuthResponse {
  token: string;
  user: User;
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
