import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The widget talks to two separate services (Plan.md section 3). Proxying
// both through the dev server keeps the browser on one origin, so local
// development needs no CORS or credential juggling.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
      "/ws": {
        target: "ws://localhost:8001",
        ws: true,
      },
    },
  },
});
