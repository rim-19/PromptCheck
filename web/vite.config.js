import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In dev, the Vite server (5173) proxies /api to the FastAPI backend (8000).
// In production, FastAPI serves the built files, so /api is same-origin.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8000",
    },
  },
  build: {
    outDir: "dist",
  },
});
