import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

// Same-origin in every environment: the dev server proxies /api to Django, so the session + CSRF cookies just work.
const target = process.env.VITE_PROXY_TARGET ?? "http://127.0.0.1:8020";
const proxy = {
  "/api": { target, changeOrigin: true },
  "/health": { target, changeOrigin: true },
};

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) } },
  server: { port: 5193, proxy },
  preview: { port: 4193, proxy },
  build: {
    rollupOptions: {
      output: {
        manualChunks(id: string) {
          if (!id.includes("node_modules")) return undefined;
          if (/node_modules\/(react|react-dom|react-router|react-router-dom|scheduler)\//.test(id)) return "react";
          if (/node_modules\/@fullcalendar\/|node_modules\/luxon\/|node_modules\/preact/.test(id)) return "calendar";
          if (/node_modules\/(@tanstack|react-hook-form|zod|@hookform)\//.test(id)) return "data";
          if (/node_modules\/(radix-ui|@radix-ui)\//.test(id)) return "ui";
          return undefined;
        },
      },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    css: false,
    exclude: ["e2e/**", "node_modules/**"],
  },
});
