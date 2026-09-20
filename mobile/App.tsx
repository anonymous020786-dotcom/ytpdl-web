import { NavigationContainer, DarkTheme } from "@react-navigation/native";
import { createBottomTabNavigator } from "@react-navigation/bottom-tabs";
import { StatusBar } from "expo-status-bar";
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from "react-native";

import { AuthProvider, useAuth } from "./src/auth/AuthContext";
import { LoginScreen } from "./src/screens/LoginScreen";
import { HomeScreen } from "./src/screens/HomeScreen";
import { JobsScreen } from "./src/screens/JobsScreen";
import { SubscriptionsScreen } from "./src/screens/SubscriptionsScreen";

const Tab = createBottomTabNavigator();

const theme = {
  ...DarkTheme,
  colors: { ...DarkTheme.colors, background: "#14161a", card: "#1d2026", primary: "#e51c23", border: "#2c3038" },
};

function Header() {
  const { user, logout } = useAuth();
  return (
    <View style={styles.header}>
      <Text style={styles.headerTitle}>YT Playlist Downloader</Text>
      <View style={styles.headerRight}>
        <Text style={styles.headerEmail} numberOfLines={1}>
          {user?.email}
        </Text>
        <Pressable onPress={logout}>
          <Text style={styles.logout}>Log out</Text>
        </Pressable>
      </View>
    </View>
  );
}

function MainTabs() {
  return (
    <View style={{ flex: 1 }}>
      <Header />
      <Tab.Navigator screenOptions={{ headerShown: false, tabBarStyle: { backgroundColor: "#1d2026" } }}>
        <Tab.Screen name="Home">{() => <HomeScreen onQueued={() => {}} />}</Tab.Screen>
        <Tab.Screen name="Jobs" component={JobsScreen} />
        <Tab.Screen name="Subscriptions" component={SubscriptionsScreen} />
      </Tab.Navigator>
    </View>
  );
}

function Root() {
  const { user, loading } = useAuth();
  if (loading) {
    return (
      <View style={styles.loading}>
        <ActivityIndicator color="#e51c23" size="large" />
      </View>
    );
  }
  return user ? <MainTabs /> : <LoginScreen />;
}

export default function App() {
  return (
    <AuthProvider>
      <NavigationContainer theme={theme}>
        <Root />
        <StatusBar style="light" />
      </NavigationContainer>
    </AuthProvider>
  );
}

const styles = StyleSheet.create({
  loading: { flex: 1, backgroundColor: "#14161a", alignItems: "center", justifyContent: "center" },
  header: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    padding: 16,
    paddingTop: 56,
    backgroundColor: "#14161a",
    borderBottomWidth: 1,
    borderBottomColor: "#2c3038",
  },
  headerTitle: { color: "#e6e6e6", fontSize: 16, fontWeight: "700" },
  headerRight: { flexDirection: "row", alignItems: "center", gap: 10, maxWidth: 180 },
  headerEmail: { color: "#8a8f98", fontSize: 12, flexShrink: 1 },
  logout: { color: "#e51c23", fontSize: 12, textDecorationLine: "underline" },
});
