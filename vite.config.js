import { fileURLToPath } from "node:url";
import { defineConfig, loadEnv } from "vite";

const root = fileURLToPath(new URL("./web", import.meta.url));

const projectRoot = fileURLToPath(new URL("./", import.meta.url));

export default defineConfig(({ mode, command }) => {
  // Read ports in Node only; API credentials are never injected into browser code.
  const env = loadEnv(mode, projectRoot, "");
  const port = Number(process.env.PORT || env.PORT || 8765);
  const apiPort = Number(process.env.API_PORT || env.API_PORT || 8766);
  if (command === "serve") {
    for (const value of [port, apiPort]) {
      if (!Number.isInteger(value) || value < 1 || value > 65535) throw new Error("PORT and API_PORT must be valid TCP ports.");
    }
    if (port === apiPort) throw new Error("PORT and API_PORT must differ in development.");
  }
  return {
    root,
    envDir: projectRoot,
    // This app has no public environment variables. Never inject .env values,
    // including accidentally VITE_-prefixed credentials, into browser modules.
    envPrefix: [],
    server: {
      host: "127.0.0.1",
      port,
      strictPort: true,
      fs: { strict: true, allow: [root] },
      proxy: {
        // Match the API path segment, not frontend modules such as /api.js.
        "^/api(?:/|$)": {
          target: "http://127.0.0.1:" + apiPort,
          // Preserve the browser-facing Host so the API can compare it to Origin.
          // Vite's string shorthand enables changeOrigin and breaks this check.
          changeOrigin: false,
        },
      },
    },
    build: {
      outDir: fileURLToPath(new URL("./dist", import.meta.url)),
      emptyOutDir: true,
    },
  };
});
