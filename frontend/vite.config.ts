import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { VitePWA } from "vite-plugin-pwa";

// The backend port; keep in sync with .env PORT. Used only for the dev proxy.
const BACKEND_PORT = process.env.PORT ?? "3002";

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: "autoUpdate",
      includeAssets: ["icons/favicon-32.png", "icons/apple-touch-icon.png"],
      manifest: {
        name: "台灣華語老師",
        short_name: "華語老師",
        description:
          "Personal Taiwanese Mandarin teacher — lessons, review, listening, tones, and conversation.",
        lang: "zh-Hant-TW",
        theme_color: "#00694E",
        background_color: "#F6F4EC",
        display: "standalone",
        orientation: "portrait",
        start_url: "/",
        scope: "/",
        icons: [
          { src: "icons/icon-192.png", sizes: "192x192", type: "image/png", purpose: "any maskable" },
          { src: "icons/icon-512.png", sizes: "512x512", type: "image/png", purpose: "any maskable" },
        ],
      },
      workbox: {
        // Don't try to cache/handle the API or audio — those are server-owned.
        // /reset must never be handled by the service worker — it is the page
        // that removes a service worker stuck in an update-reload cycle.
        navigateFallbackDenylist: [/^\/api/, /^\/audio/, /^\/reset/],
        // Drop precaches from previous builds. Without this the old bundles stay
        // resident after a rebuild, and with `autoUpdate` above the stale page
        // can update-and-reload in a loop instead of settling on the new build.
        cleanupOutdatedCaches: true,
      },
    }),
  ],
  server: {
    host: true,
    port: 5173,
    proxy: {
      "/api": `http://localhost:${BACKEND_PORT}`,
      "/audio": `http://localhost:${BACKEND_PORT}`,
    },
  },
  build: {
    outDir: "dist",
  },
});
