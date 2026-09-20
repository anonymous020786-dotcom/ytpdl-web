import { useEffect, useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";

import { api } from "../api/client";
import { saveJobFile } from "../api/download";
import type { JobFile, JobRecord } from "../api/types";

const ACTIVE_STATES = new Set(["queued", "running", "paused"]);

interface Props {
  job: JobRecord;
  onCancel: (jobId: string) => void;
  onPause: (jobId: string) => void;
  onResume: (jobId: string) => void;
}

export function JobRow({ job, onCancel, onPause, onResume }: Props) {
  const [files, setFiles] = useState<JobFile[]>([]);
  const [savingFile, setSavingFile] = useState<string | null>(null);

  useEffect(() => {
    if (job.state === "completed") {
      api.jobFiles(job.job_id).then(setFiles).catch(() => {});
    }
  }, [job.state, job.job_id]);

  const percent = Number(job.percent || 0);

  async function handleSave(name: string) {
    setSavingFile(name);
    try {
      await saveJobFile(job.job_id, name);
    } catch {
      // saveJobFile failures surface via the OS share sheet not appearing;
      // a toast library isn't wired up yet, so this is silently best-effort.
    } finally {
      setSavingFile(null);
    }
  }

  return (
    <View style={styles.row}>
      <View style={styles.head}>
        <Text style={styles.title} numberOfLines={1}>
          {job.title || job.job_id}
        </Text>
        <View style={[styles.badge, styles[`badge_${job.state}` as keyof typeof styles] as object]}>
          <Text style={styles.badgeText}>{job.state}</Text>
        </View>
      </View>

      <View style={styles.progressBar}>
        <View style={[styles.progressFill, { width: `${Math.min(100, percent)}%` }]} />
      </View>

      <View style={styles.meta}>
        <Text style={styles.metaText}>{job.status}</Text>
        {!!job.speed && <Text style={styles.metaText}>{job.speed}</Text>}
        {!!job.eta && <Text style={styles.metaText}>ETA {job.eta}</Text>}
        <Text style={styles.metaText}>
          {job.done}/{job.total}
        </Text>
      </View>

      {!!job.error && <Text style={styles.error}>{job.error}</Text>}

      {ACTIVE_STATES.has(job.state) && (
        <View style={styles.actions}>
          {job.state === "running" && (
            <Pressable onPress={() => onPause(job.job_id)}>
              <Text style={styles.link}>Pause</Text>
            </Pressable>
          )}
          {job.state === "paused" && (
            <Pressable onPress={() => onResume(job.job_id)}>
              <Text style={styles.link}>Resume</Text>
            </Pressable>
          )}
          <Pressable onPress={() => onCancel(job.job_id)}>
            <Text style={styles.link}>Cancel</Text>
          </Pressable>
        </View>
      )}

      {files.map((f) => (
        <Pressable key={f.name} onPress={() => handleSave(f.name)} style={styles.fileRow}>
          <Text style={styles.link} numberOfLines={1}>
            {savingFile === f.name ? "Saving…" : f.name}
          </Text>
          <Text style={styles.muted}>({(f.size / 1_048_576).toFixed(1)} MiB)</Text>
        </Pressable>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  row: { backgroundColor: "#1d2026", borderRadius: 10, padding: 14, marginBottom: 10 },
  head: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: 8, gap: 8 },
  title: { color: "#e6e6e6", fontWeight: "600", flex: 1 },
  badge: { paddingHorizontal: 8, paddingVertical: 3, borderRadius: 999, backgroundColor: "#2c3038" },
  badge_running: { backgroundColor: "#2196f3" },
  badge_completed: { backgroundColor: "#4caf50" },
  badge_failed: { backgroundColor: "#a20025" },
  badge_cancelled: { backgroundColor: "#647687" },
  badge_paused: { backgroundColor: "#ff9800" },
  badgeText: { color: "#fff", fontSize: 11, textTransform: "uppercase" },
  progressBar: { height: 6, backgroundColor: "#2c3038", borderRadius: 999, overflow: "hidden" },
  progressFill: { height: "100%", backgroundColor: "#e51c23" },
  meta: { flexDirection: "row", gap: 12, marginTop: 6, flexWrap: "wrap" },
  metaText: { color: "#8a8f98", fontSize: 12 },
  error: { color: "#ff6b6b", marginTop: 6 },
  actions: { flexDirection: "row", gap: 16, marginTop: 8 },
  link: { color: "#e51c23", textDecorationLine: "underline" },
  fileRow: { flexDirection: "row", alignItems: "center", gap: 8, marginTop: 8 },
  muted: { color: "#8a8f98", fontSize: 12 },
});
