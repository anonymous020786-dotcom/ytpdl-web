import { useState } from "react";
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";

import { api, ApiError } from "../api/client";
import type { DownloadSettingsInput, ResolvedSource } from "../api/types";

const DEFAULT_SETTINGS: DownloadSettingsInput = {
  audio_only: false,
  audio_format: "mp3",
  video_format: "mp4",
  quality: "1080",
  convert: false,
  embed_thumbnail: true,
  tag_audio: true,
  separate_playlist_folders: true,
  filename_template: "$title",
};

const AUDIO_FORMATS = ["mp3", "m4a", "opus", "flac"];
const VIDEO_FORMATS = ["mp4", "mkv", "webm"];
const QUALITIES = ["480", "720", "1080", "2160"];

export function HomeScreen({ onQueued }: { onQueued: () => void }) {
  const [url, setUrl] = useState("");
  const [resolving, setResolving] = useState(false);
  const [source, setSource] = useState<ResolvedSource | null>(null);
  const [settings, setSettings] = useState<DownloadSettingsInput>(DEFAULT_SETTINGS);
  const [queuing, setQueuing] = useState(false);
  const [error, setError] = useState("");

  async function handleResolve() {
    setError("");
    setSource(null);
    setResolving(true);
    try {
      setSource(await api.resolve(url.trim()));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't resolve that link");
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
      setError(err instanceof ApiError ? err.message : "Couldn't queue that job");
    } finally {
      setQueuing(false);
    }
  }

  return (
    <ScrollView style={styles.container} contentContainerStyle={{ padding: 16 }}>
      <View style={styles.row}>
        <TextInput
          style={styles.input}
          placeholder="Paste a YouTube video, playlist, or channel link"
          placeholderTextColor="#8a8f98"
          autoCapitalize="none"
          value={url}
          onChangeText={setUrl}
        />
        <Pressable style={styles.smallButton} onPress={handleResolve} disabled={resolving || !url.trim()}>
          {resolving ? <ActivityIndicator color="#fff" /> : <Text style={styles.buttonText}>Go</Text>}
        </Pressable>
      </View>

      {!!error && <Text style={styles.error}>{error}</Text>}

      {source && (
        <View style={styles.card}>
          <Text style={styles.cardTitle} numberOfLines={2}>
            {source.title}
          </Text>
          <Text style={styles.muted}>
            {source.kind} · {source.videos.length} item{source.videos.length === 1 ? "" : "s"}
          </Text>

          <View style={styles.optionRow}>
            <OptionButton
              label="Audio only"
              active={settings.audio_only}
              onPress={() => setSettings((s) => ({ ...s, audio_only: true }))}
            />
            <OptionButton
              label="Video"
              active={!settings.audio_only}
              onPress={() => setSettings((s) => ({ ...s, audio_only: false }))}
            />
          </View>

          {settings.audio_only ? (
            <>
              <Text style={styles.sectionLabel}>Format</Text>
              <View style={styles.optionRow}>
                {AUDIO_FORMATS.map((f) => (
                  <OptionButton
                    key={f}
                    label={f.toUpperCase()}
                    active={settings.audio_format === f}
                    onPress={() => setSettings((s) => ({ ...s, audio_format: f }))}
                  />
                ))}
              </View>
            </>
          ) : (
            <>
              <Text style={styles.sectionLabel}>Quality</Text>
              <View style={styles.optionRow}>
                {QUALITIES.map((q) => (
                  <OptionButton
                    key={q}
                    label={`${q}p`}
                    active={settings.quality === q}
                    onPress={() => setSettings((s) => ({ ...s, quality: q }))}
                  />
                ))}
              </View>
              <Text style={styles.sectionLabel}>Format</Text>
              <View style={styles.optionRow}>
                {VIDEO_FORMATS.map((f) => (
                  <OptionButton
                    key={f}
                    label={f.toUpperCase()}
                    active={settings.video_format === f}
                    onPress={() => setSettings((s) => ({ ...s, video_format: f, convert: true }))}
                  />
                ))}
              </View>
            </>
          )}

          <Pressable style={styles.button} onPress={handleQueue} disabled={queuing}>
            {queuing ? (
              <ActivityIndicator color="#fff" />
            ) : (
              <Text style={styles.buttonText}>
                Download {source.videos.length} item{source.videos.length === 1 ? "" : "s"}
              </Text>
            )}
          </Pressable>
        </View>
      )}
    </ScrollView>
  );
}

function OptionButton({ label, active, onPress }: { label: string; active: boolean; onPress: () => void }) {
  return (
    <Pressable style={[styles.option, active && styles.optionActive]} onPress={onPress}>
      <Text style={[styles.optionText, active && styles.optionTextActive]}>{label}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#14161a" },
  row: { flexDirection: "row", gap: 8 },
  input: {
    flex: 1,
    backgroundColor: "#0f1115",
    borderWidth: 1,
    borderColor: "#2c3038",
    borderRadius: 8,
    padding: 12,
    color: "#e6e6e6",
  },
  smallButton: { backgroundColor: "#e51c23", borderRadius: 8, paddingHorizontal: 18, justifyContent: "center" },
  button: { backgroundColor: "#e51c23", borderRadius: 8, padding: 14, alignItems: "center", marginTop: 16 },
  buttonText: { color: "#fff", fontWeight: "700" },
  error: { color: "#ff6b6b", marginTop: 10 },
  card: { backgroundColor: "#1d2026", borderRadius: 10, padding: 16, marginTop: 16 },
  cardTitle: { color: "#e6e6e6", fontWeight: "700", fontSize: 16 },
  muted: { color: "#8a8f98", marginTop: 4 },
  sectionLabel: { color: "#8a8f98", fontSize: 12, marginTop: 14, marginBottom: 6 },
  optionRow: { flexDirection: "row", gap: 8, flexWrap: "wrap" },
  option: { borderWidth: 1, borderColor: "#2c3038", borderRadius: 8, paddingVertical: 8, paddingHorizontal: 14 },
  optionActive: { backgroundColor: "#e51c23", borderColor: "#e51c23" },
  optionText: { color: "#8a8f98", fontWeight: "600" },
  optionTextActive: { color: "#fff" },
});
