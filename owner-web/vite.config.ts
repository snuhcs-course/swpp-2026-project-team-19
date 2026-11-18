import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// The API serves the build at /owner/ (backend/app/owner_web). In development, `npm run dev` serves the
// page here and forwards the API and the page's config to a local backend, so the code only uses
// relative paths and never names a server.
const apiTarget = process.env.BOTTLEMAP_DEV_API ?? "http://localhost:8000";

export default defineConfig({
  base: "/owner/",
  plugins: [react()],
  server: {
    proxy: {
      "/api": apiTarget,
      "/owner/config.js": apiTarget,
    },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
  },
});
