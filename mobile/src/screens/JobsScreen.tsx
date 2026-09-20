import { useCallback, useEffect, useState } from "react";
import { FlatList, RefreshControl, StyleSheet, Text, View } from "react-native";
import { useFocusEffect } from "@react-navigation/native";

import { api } from "../api/client";
import { JobRow } from "../components/JobRow";
import type { JobRecord } from "../api/types";
import { useJobEvents } from "../ws/useJobEvents";

export function JobsScreen() {
  const [jobs, setJobs] = useState<JobRecord[]>([]);
  const [refreshing, setRefreshing] = useState(false);

  const refresh = useCallback(async () => {
    try {
      setJobs(await api.listJobs());
    } catch {
      // handled by the auth layer if this is a 401; otherwise just retry next pull
    }
  }, []);

  // Refresh on mount and every time this tab regains focus — e.g. right
  // after queuing a job from the Home tab — not just on the 15s poll.
  useFocusEffect(
    useCallback(() => {
      refresh();
    }, [refresh])
  );

  useEffect(() => {
    const poll = setInterval(refresh, 15000); // safety net if the socket drops
    return () => clearInterval(poll);
  }, [refresh]);

  useJobEvents(
    (event) => {
      setJobs((prev) => {
        const idx = prev.findIndex((j) => j.job_id === event.job_id);
        if (idx === -1) return prev; // job queued before this screen mounted — next poll picks it up
        const updated = { ...prev[idx] };
        for (const [key, value] of Object.entries(event)) {
          if (key === "job_id" || key === "type") continue;
          (updated as Record<string, string>)[key] = String(value);
        }
        const next = [...prev];
        next[idx] = updated;
        return next;
      });
    },
    true
  );

  async function handlePull() {
    setRefreshing(true);
    await refresh();
    setRefreshing(false);
  }

  return (
    <FlatList
      style={styles.container}
      contentContainerStyle={{ padding: 16 }}
      data={jobs}
      keyExtractor={(j) => j.job_id}
      renderItem={({ item }) => (
        <JobRow
          job={item}
          onCancel={(id) => api.cancelJob(id)}
          onPause={(id) => api.pauseJob(id)}
          onResume={(id) => api.resumeJob(id)}
        />
      )}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={handlePull} tintColor="#e51c23" />}
      ListEmptyComponent={
        <View style={styles.empty}>
          <Text style={styles.emptyText}>No downloads yet — paste a link on the Home tab.</Text>
        </View>
      }
    />
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#14161a" },
  empty: { paddingTop: 60, alignItems: "center" },
  emptyText: { color: "#8a8f98" },
});
