import { useEffect, useState } from "react";
import { KeyboardAvoidingView, Platform, Pressable, StyleSheet, Text, TextInput } from "react-native";

import { getApiBaseUrl, setApiBaseUrl } from "../config";

export function SettingsScreen() {
  const [serverUrl, setServerUrl] = useState("");
  const [serverSaved, setServerSaved] = useState(false);

  useEffect(() => {
    getApiBaseUrl().then(setServerUrl);
  }, []);

  async function saveServerUrl() {
    await setApiBaseUrl(serverUrl);
    setServerSaved(true);
    setTimeout(() => setServerSaved(false), 1500);
  }

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
    >
      <Text style={styles.title}>Server address</Text>
      <Text style={styles.serverLabel}>
        Backend URL — e.g. http://192.168.1.20:8000. A LAN IP changes when your router
        reassigns it; update it here any time without reinstalling the app.
      </Text>
      <TextInput
        style={styles.input}
        placeholder="http://192.168.1.20:8000"
        placeholderTextColor="#8a8f98"
        autoCapitalize="none"
        autoCorrect={false}
        keyboardType="url"
        value={serverUrl}
        onChangeText={setServerUrl}
      />
      <Pressable style={styles.button} onPress={saveServerUrl}>
        <Text style={styles.buttonText}>{serverSaved ? "Saved ✓" : "Save"}</Text>
      </Pressable>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#14161a", padding: 24 },
  title: { color: "#e6e6e6", fontSize: 18, fontWeight: "600", marginBottom: 12 },
  input: {
    backgroundColor: "#0f1115",
    borderWidth: 1,
    borderColor: "#2c3038",
    borderRadius: 8,
    padding: 12,
    color: "#e6e6e6",
    marginBottom: 12,
  },
  button: { backgroundColor: "#e51c23", borderRadius: 8, padding: 14, alignItems: "center" },
  buttonText: { color: "#fff", fontWeight: "700", fontSize: 16 },
  serverLabel: { color: "#8a8f98", fontSize: 12, marginBottom: 12, lineHeight: 16 },
});
