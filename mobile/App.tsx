import { NavigationContainer, DarkTheme } from "@react-navigation/native";
import { createBottomTabNavigator } from "@react-navigation/bottom-tabs";
import { StatusBar } from "expo-status-bar";
import { StyleSheet, Text, View } from "react-native";

import { HomeScreen } from "./src/screens/HomeScreen";
import { JobsScreen } from "./src/screens/JobsScreen";
import { SubscriptionsScreen } from "./src/screens/SubscriptionsScreen";
import { SettingsScreen } from "./src/screens/SettingsScreen";

const Tab = createBottomTabNavigator();

const theme = {
  ...DarkTheme,
  colors: { ...DarkTheme.colors, background: "#14161a", card: "#1d2026", primary: "#e51c23", border: "#2c3038" },
};

function Header() {
  return (
    <View style={styles.header}>
      <Text style={styles.headerTitle}>YT Playlist Downloader</Text>
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
        <Tab.Screen name="Settings" component={SettingsScreen} />
      </Tab.Navigator>
    </View>
  );
}

export default function App() {
  return (
    <NavigationContainer theme={theme}>
      <MainTabs />
      <StatusBar style="light" />
    </NavigationContainer>
  );
}

const styles = StyleSheet.create({
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
});
