import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// PORT / BACKEND_PORT env vars let parallel dev instances avoid port clashes.
const devPort = Number(process.env.PORT) || 5173;
const backendPort = Number(process.env.BACKEND_PORT) || 8000;
const apiTarget = `http://127.0.0.1:${backendPort}`;
// Stock AI RAG service (lm/), runs separately on its own port
const lmPort = Number(process.env.LM_PORT) || 8010;

export default defineConfig({
  plugins: [react()],
  server: {
    port: devPort,
    proxy: {
      "/api": {
        target: apiTarget,
        changeOrigin: true,
        timeout: 600000,
      },
      "/lm-api": {
        target: `http://127.0.0.1:${lmPort}`,
        changeOrigin: true,
        timeout: 600000,
        rewrite: (path) => path.replace(/^\/lm-api/, "/api"),
      },
      "/health": {
        target: apiTarget,
        changeOrigin: true,
      },
      "/ws": {
        target: `ws://127.0.0.1:${backendPort}`,
        ws: true,
        changeOrigin: true,
      },
      "/sse": {
        target: apiTarget,
        changeOrigin: true,
      },
    },
  },
});
