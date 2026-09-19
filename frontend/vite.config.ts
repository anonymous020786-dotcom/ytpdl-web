import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev server proxies /api and /ws to the backend so the frontend can be run
// standalone with `npm run dev` without CORS fuss. In production, Caddy does
// this same proxying (see /Caddyfile) in front of the built static files.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": "http://localhost:8000",
      "/ws": { target: "ws://localhost:8000", ws: true },
    },
  },
});
