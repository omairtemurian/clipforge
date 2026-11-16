import { defineConfig, devices } from "@playwright/test";
import { fileURLToPath } from "node:url";

const e2eDir = fileURLToPath(new URL(".", import.meta.url));
const fixturesDir = fileURLToPath(
  new URL("../backend/tests/fixtures", import.meta.url),
);

const modelsDir = fileURLToPath(new URL("../models", import.meta.url));

const BACKEND_URL = "http://127.0.0.1:8000";
const FRONTEND_URL = "http://localhost:5173";

// The backend runs in test mode (fixture transcript, recorded LLM reply) from
// a fresh .run directory that is its cwd and data dir, so the owner's data,
// .env.local and config.yaml are never read or written.
const backendCommand = [
  "rm -rf .run",
  "mkdir .run",
  "cd .run",
  "uv run --project ../.. uvicorn --factory clipforge.api.testapp:create_test_app" +
    " --host 127.0.0.1 --port 8000",
].join(" && ");

export default defineConfig({
  testDir: ".",
  testMatch: "*.spec.ts",
  outputDir: "./.results",
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  reporter: "list",
  use: {
    baseURL: FRONTEND_URL,
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command: backendCommand,
      cwd: e2eDir,
      url: `${BACKEND_URL}/api/projects`,
      reuseExistingServer: false,
      timeout: 120_000,
      env: {
        CLIPFORGE_TEST_MODE: "1",
        CLIPFORGE_FIXTURES_DIR: fixturesDir,
        DATA_DIR: "data",
        // The signals and reframe steps load YAMNet and the face model from
        // the project's models/ (`make setup` downloads them); never fetched.
        MODELS_DIR: modelsDir,
      },
    },
    {
      command:
        "npm --prefix ../frontend run dev -- --host localhost --port 5173",
      cwd: e2eDir,
      url: FRONTEND_URL,
      reuseExistingServer: false,
      timeout: 60_000,
    },
  ],
});
