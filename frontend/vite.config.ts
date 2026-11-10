import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "path";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  define: {
    "process.env.NODE_ENV": JSON.stringify(process.env.NODE_ENV ?? "development"),
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "https://127.0.0.1:8443",
        secure: false,
      },
      "/camera": {
        target: "https://127.0.0.1:8443",
        secure: false,
      },
      "/ws": {
        target: "wss://127.0.0.1:8765",
        ws: true,
        secure: false,
      },
    },
  },
  build: {
    outDir: "../public",
    emptyOutDir: true,
  },
});
