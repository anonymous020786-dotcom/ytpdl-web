import { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, FlatList, Pressable, StyleSheet, Text, TextInput, View } from "react-native";

import { api, ApiError } from "../api/client";
import type { Subscription } from "../api/types";

function timeAgo(unixSeconds: number): string {
  if (!unixSeconds) return "never";
  const seconds = Math.max(0, Date.now() / 1000 - unixSeconds);
  if (seconds < 90) return "just now";
  const minutes = Math.round(seconds / 60);
  if (minutes < 90) return `${minutes}m ago`;
  return `${Math.round(minutes / 60)}h ago`;
}

export function SubscriptionsScreen() {
  const [subs, setSubs] = useState<Subscription[]>([]);
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const refresh = useCallback(() => {
    api.listSubscriptions().then(setSubs).catch(() => {});
  }, []);

  useEffect(() => {
    refresh();
    const poll = setInterval(refresh, 20000);
    return () => clearInterval(poll);
  }, [refresh]);

  async function handleAdd() {
    setBusy(true);
    setError("");
    try {
      await api.createSubscription(url.trim(), 60);
      setUrl("");
      refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't subscribe to that link");
    } finally {
      setBusy(false);
    }
  }

  return (
    <View style={styles.container}>
      <View style={styles.row}>
        <TextInput
          style={styles.input}
          placeholder="Channel or playlist link to watch"
          placeholderTextColor="#8a8f98"
          autoCapitalize="none"
          value={url}
          onChangeText={setUrl}
        />
        <Pressable style={styles.smallButton} onPress={handleAdd} disabled={busy || !url.trim()}>
          {busy ? <ActivityIndicator color="#fff" /> : <Text style={styles.buttonText}>Add</Text>}
        </Pressable>
      </View>
      {!!error && <Text style={styles.error}>{error}</Text>}

      <FlatList
        contentContainerStyle={{ padding: 16 }}
        data={subs}
        keyExtractor={(s) => s.id}
        renderItem={({ item }) => (
          <View style={styles.subRow}>
            <View style={{ flex: 1 }}>
              <Text style={styles.subTitle} numberOfLines={1}>
                {item.title || item.url}
              </Text>
              <Text style={styles.muted}>
                {item.kind} · every {item.interval_minutes}m · checked {timeAgo(item.last_checked)}
              </Text>
            </View>
            <Pressable onPress={() => api.checkSubscription(item.id)}>
              <Text style={styles.link}>Check now</Text>
            </Pressable>
            <Pressable
              onPress={async () => {
                await api.deleteSubscription(item.id);
                refresh();
              }}
            >
              <Text style={styles.link}>Remove</Text>
            </Pressable>
          </View>
        )}
        ListEmptyComponent={
          <View style={styles.empty}>
            <Text style={styles.muted}>
              No subscriptions — new uploads from a channel or playlist get auto-queued once you add one.
            </Text>
          </View>
        }
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#14161a", paddingTop: 16 },
  row: { flexDirection: "row", gap: 8, paddingHorizontal: 16 },
  input: {
    flex: 1,
    backgroundColor: "#0f1115",
    borderWidth: 1,
    borderColor: "#2c3038",
    borderRadius: 8,
    padding: 12,
    color: "#e6e6e6",
  },
  smallButton: { backgroundColor: "#e51c23", borderRadius: 8, paddingHorizontal: 16, justifyContent: "center" },
  buttonText: { color: "#fff", fontWeight: "700" },
  error: { color: "#ff6b6b", marginTop: 10, marginHorizontal: 16 },
  subRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 14,
    backgroundColor: "#1d2026",
    borderRadius: 10,
    padding: 14,
    marginBottom: 10,
  },
  subTitle: { color: "#e6e6e6", fontWeight: "600" },
  muted: { color: "#8a8f98", fontSize: 12, marginTop: 2 },
  link: { color: "#e51c23", textDecorationLine: "underline", fontSize: 12 },
  empty: { paddingTop: 40, alignItems: "center" },
});
