import { useState } from "react";
import { api } from "../api";
import type { DownloadSettingsInput, ResolvedSource } from "../types";

const DEFAULT_SETTINGS: DownloadSettingsInput = {
  audio_only: false,
  audio_format: "mp3",
  video_format: "mp4",
  quality: "1080",
  convert: false,
  download_subtitles: false,
  subtitle_languages: "en",
  embed_thumbnail: true,
  tag_audio: true,
  separate_playlist_folders: true,
  filename_template: "$title",
};

export function SubmitForm({ onQueued }: { onQueued: () => void }) {
  const [url, setUrl] = useState("");
  const [resolving, setResolving] = useState(false);
  const [source, setSource] = useState<ResolvedSource | null>(null);
  const [settings, setSettings] = useState<DownloadSettingsInput>(DEFAULT_SETTINGS);
  const [error, setError] = useState("");
  const [queuing, setQueuing] = useState(false);

  async function handleResolve(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setSource(null);
    setResolving(true);
    try {
      setSource(await api.resolve(url));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setResolving(false);
    }
  }

  async function handleQueue() {
    if (!source) return;
    setQueuing(true);
    setError("");
    try {
      await api.createJob(source, settings);
      setSource(null);
      setUrl("");
      onQueued();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setQueuing(false);
    }
  }

  return (
    <div className="card">
      <form onSubmit={handleResolve} className="row">
        <input
          type="text"
          placeholder="Paste a YouTube video, playlist or channel link"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          required
        />
        <button type="submit" disabled={resolving}>
          {resolving ? "Resolving…" : "Resolve"}
        </button>
      </form>

      {error && <p className="error">{error}</p>}

      {source && (
        <div className="resolved">
          <p>
            <strong>{source.title}</strong> — {source.kind} — {source.videos.length} item
            {source.videos.length === 1 ? "" : "s"}
          </p>

          <div className="settings-grid">
            <label>
              <input
                type="checkbox"
                checked={settings.audio_only}
                onChange={(e) => setSettings({ ...settings, audio_only: e.target.checked })}
              />
              Audio only
            </label>

            {settings.audio_only ? (
              <label>
                Format
                <select
                  value={settings.audio_format}
                  onChange={(e) => setSettings({ ...settings, audio_format: e.target.value })}
                >
                  {["mp3", "m4a", "aac", "opus", "flac", "wav", "ogg"].map((f) => (
                    <option key={f}>{f}</option>
                  ))}
                </select>
              </label>
            ) : (
              <>
                <label>
                  Format
                  <select
                    value={settings.video_format}
                    onChange={(e) => setSettings({ ...settings, video_format: e.target.value })}
                  >
                    {["mp4", "mkv", "webm", "mov"].map((f) => (
                      <option key={f}>{f}</option>
                    ))}
                  </select>
                </label>
                <label>
                  Max quality
                  <select
                    value={settings.quality}
                    onChange={(e) => setSettings({ ...settings, quality: e.target.value })}
                  >
                    {["144", "240", "360", "480", "720", "1080", "1440", "2160"].map((q) => (
                      <option key={q}>{q}p</option>
                    ))}
                  </select>
                </label>
              </>
            )}

            <label>
              <input
                type="checkbox"
                checked={settings.embed_thumbnail}
                onChange={(e) => setSettings({ ...settings, embed_thumbnail: e.target.checked })}
              />
              Embed thumbnail
            </label>
            <label>
              <input
                type="checkbox"
                checked={settings.tag_audio}
                onChange={(e) => setSettings({ ...settings, tag_audio: e.target.checked })}
              />
              Auto-tag audio
            </label>
            {source.kind !== "video" && (
              <label>
                <input
                  type="checkbox"
                  checked={settings.separate_playlist_folders}
                  onChange={(e) => setSettings({ ...settings, separate_playlist_folders: e.target.checked })}
                />
                Separate folder per playlist
              </label>
            )}
            <label>
              Filename template
              <input
                type="text"
                value={settings.filename_template}
                onChange={(e) => setSettings({ ...settings, filename_template: e.target.value })}
              />
            </label>
          </div>

          <button onClick={handleQueue} disabled={queuing}>
            {queuing ? "Queuing…" : `Download ${source.videos.length} item${source.videos.length === 1 ? "" : "s"}`}
          </button>
        </div>
      )}
    </div>
  );
}
