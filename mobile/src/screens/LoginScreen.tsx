import { useEffect, useState } from "react";
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";

import { useAuth } from "../auth/AuthContext";
import { ApiError } from "../api/client";
import { getApiBaseUrl, setApiBaseUrl } from "../config";

export function LoginScreen() {
  const { login, register } = useAuth();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [inviteCode, setInviteCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const [showServerSettings, setShowServerSettings] = useState(false);
  const [serverUrl, setServerUrl] = useState("");
  const [serverSaved, setServerSaved] = useState(false);

  useEffect(() => {
    getApiBaseUrl().then(setServerUrl);
  }, []);

  async function submit() {
    setBusy(true);
    setError("");
    try {
      if (mode === "login") {
        await login(email.trim(), password);
      } else {
        await register(email.trim(), password, inviteCode);
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  }

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
      <Text style={styles.title}>YT Playlist Downloader</Text>

      <View style={styles.tabs}>
        <Pressable
          style={[styles.tab, mode === "login" && styles.tabActive]}
          onPress={() => setMode("login")}
        >
          <Text style={[styles.tabText, mode === "login" && styles.tabTextActive]}>Log in</Text>
        </Pressable>
        <Pressable
          style={[styles.tab, mode === "register" && styles.tabActive]}
          onPress={() => setMode("register")}
        >
          <Text style={[styles.tabText, mode === "register" && styles.tabTextActive]}>Sign up</Text>
        </Pressable>
      </View>

      <TextInput
        style={styles.input}
        placeholder="Email"
        placeholderTextColor="#8a8f98"
        autoCapitalize="none"
        keyboardType="email-address"
        value={email}
        onChangeText={setEmail}
      />
      <TextInput
        style={styles.input}
        placeholder="Password"
        placeholderTextColor="#8a8f98"
        secureTextEntry
        value={password}
        onChangeText={setPassword}
      />
      {mode === "register" && (
        <TextInput
          style={styles.input}
          placeholder="Invite code (if required)"
          placeholderTextColor="#8a8f98"
          value={inviteCode}
          onChangeText={setInviteCode}
        />
      )}

      {!!error && <Text style={styles.error}>{error}</Text>}

      <Pressable style={styles.button} onPress={submit} disabled={busy}>
        {busy ? (
          <ActivityIndicator color="#fff" />
        ) : (
          <Text style={styles.buttonText}>{mode === "login" ? "Log in" : "Create account"}</Text>
        )}
      </Pressable>

      <Pressable style={styles.serverToggle} onPress={() => setShowServerSettings((v) => !v)}>
        <Text style={styles.serverToggleText}>
          {showServerSettings ? "Hide" : "Can't connect? Set"} server address
        </Text>
      </Pressable>

      {showServerSettings && (
        <View style={styles.serverBox}>
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
          <Pressable style={styles.serverSaveButton} onPress={saveServerUrl}>
            <Text style={styles.buttonText}>{serverSaved ? "Saved ✓" : "Save"}</Text>
          </Pressable>
        </View>
      )}
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#14161a", justifyContent: "center", padding: 24 },
  title: { color: "#e6e6e6", fontSize: 22, fontWeight: "600", marginBottom: 24, textAlign: "center" },
  tabs: { flexDirection: "row", gap: 4, marginBottom: 16 },
  tab: { flex: 1, paddingVertical: 10, borderRadius: 8, backgroundColor: "#1d2026", alignItems: "center" },
  tabActive: { backgroundColor: "#e51c23" },
  tabText: { color: "#8a8f98", fontWeight: "600" },
  tabTextActive: { color: "#fff" },
  input: {
    backgroundColor: "#0f1115",
    borderWidth: 1,
    borderColor: "#2c3038",
    borderRadius: 8,
    padding: 12,
    color: "#e6e6e6",
    marginBottom: 12,
  },
  error: { color: "#ff6b6b", marginBottom: 12 },
  button: { backgroundColor: "#e51c23", borderRadius: 8, padding: 14, alignItems: "center" },
  buttonText: { color: "#fff", fontWeight: "700", fontSize: 16 },
  serverToggle: { marginTop: 20, alignItems: "center" },
  serverToggleText: { color: "#8a8f98", fontSize: 12, textDecorationLine: "underline" },
  serverBox: { marginTop: 14, backgroundColor: "#1d2026", borderRadius: 10, padding: 14 },
  serverLabel: { color: "#8a8f98", fontSize: 12, marginBottom: 10, lineHeight: 16 },
  serverSaveButton: { backgroundColor: "#2c3038", borderRadius: 8, padding: 10, alignItems: "center" },
});
