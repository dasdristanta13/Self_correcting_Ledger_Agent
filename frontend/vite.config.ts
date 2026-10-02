/// <reference types="vitest/config" />
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import path from "node:path";

export default defineConfig({
  plugins: [react()],
  resolve: { alias: { "@contracts": path.resolve(__dirname, "../contracts") } },
  server: { port: 5173, proxy: { "/api": "http://localhost:8000" }, fs: { allow: [".."] } },
  test: { environment: "jsdom", globals: true, setupFiles: "./src/test/setup.ts" },
});
