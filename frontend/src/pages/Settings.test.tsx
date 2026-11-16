import { QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { createQueryClient } from "@/api/queryClient";
import type { SettingsView } from "@/api/types";
import { Toaster } from "@/components/Toaster";
import { clearToasts } from "@/lib/toast";
import {
  callsTo as callsToUrl,
  json,
  mockRoutes,
  SAVED_SETTINGS as SAVED,
  usageSummary,
} from "@/testing/mockApi";
import { SettingsPage } from "./SettingsPage";

function renderPage() {
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter>
        <SettingsPage />
      </MemoryRouter>
      <Toaster />
    </QueryClientProvider>,
  );
}

// The Settings form saves with the language model tried first.
const SAVE = "/api/settings?verify_llm=true";

function routes(extra: Parameters<typeof mockRoutes>[0] = {}) {
  const renamed = Object.fromEntries(
    Object.entries(extra).map(([key, handler]) => [
      key === "PUT /api/settings" ? `PUT ${SAVE}` : key,
      handler,
    ]),
  );
  return mockRoutes({
    "GET /api/settings": () => json(SAVED),
    "GET /api/engines": () => json([]),
    "GET /api/usage": () => json(usageSummary()),
    "POST /api/settings/models": () => json({ models: [], error: null }),
    ...renamed,
  });
}

function callsTo(
  fetchMock: Parameters<typeof callsToUrl>[0],
  method: string,
  url: string,
) {
  const saving = method === "PUT" && url === "/api/settings";
  return callsToUrl(fetchMock, method, saving ? SAVE : url);
}

function bodyOf(call: unknown[]) {
  return JSON.parse((call[1] as RequestInit).body as string) as unknown;
}

/** The language model card; other cards have write-only keys as well. */
function llmSection() {
  return screen.getByRole("region", { name: "Language model" });
}

afterEach(() => act(() => clearToasts()));

describe("Settings page", () => {
  it("shows the saved settings and never a key", async () => {
    routes();
    renderPage();

    expect(await screen.findByLabelText("Model")).toHaveValue(
      "claude-sonnet-5.5",
    );
    expect(screen.getByLabelText("GitHub account")).toHaveValue("");
    expect(screen.getByLabelText("Whisper model")).toHaveValue("small");
    expect(screen.getByLabelText("Credit template")).toHaveValue(
      "Credit: {channel}",
    );
    expect(within(llmSection()).getByText("Not set")).toBeVisible();
    expect(
      screen.getByRole("button", { name: "Save settings" }),
    ).toBeDisabled();

    await userEvent.click(screen.getByRole("radio", { name: /OpenAI/ }));
    const key = screen.getByLabelText("API key");
    expect(key).toHaveValue("");
    expect(key).toHaveAttribute("type", "password");
    expect(within(llmSection()).getByText("Saved")).toBeVisible();
    expect(document.body.innerHTML).not.toMatch(/sk-/);
  });

  it("saves only what changed, with the typed key", async () => {
    const fetchMock = routes({
      "PUT /api/settings": () =>
        json({
          ...SAVED,
          llm_provider: "openai",
          llm_model: "gpt-5",
          github_copilot_token_set: true,
        } satisfies SettingsView),
    });
    renderPage();
    await screen.findByLabelText("Model");

    await userEvent.click(screen.getByRole("radio", { name: /OpenAI/ }));
    await userEvent.clear(screen.getByLabelText("Model"));
    await userEvent.type(screen.getByLabelText("Model"), "gpt-5");
    await userEvent.type(screen.getByLabelText("API key"), "sk-secret");
    await userEvent.click(
      screen.getByRole("button", { name: "Save settings" }),
    );

    const puts = callsTo(fetchMock, "PUT", "/api/settings");
    expect(puts).toHaveLength(1);
    expect(bodyOf(puts[0])).toEqual({
      llm_provider: "openai",
      llm_model: "gpt-5",
      openai_api_key: "sk-secret",
    });
    expect(await screen.findByText("Settings saved.")).toBeVisible();
    expect(screen.getByLabelText("API key")).toHaveValue("");
    expect(
      screen.getByRole("button", { name: "Save settings" }),
    ).toBeDisabled();
  });

  it("saves the always-included hashtags from the Posting section", async () => {
    const fetchMock = routes({
      "PUT /api/settings": () =>
        json({ ...SAVED, always_hashtags: ["pizza"] } satisfies SettingsView),
    });
    renderPage();
    await screen.findByLabelText("Model");

    await userEvent.type(
      screen.getByLabelText("Always include these hashtags"),
      "#pizza{Enter}",
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Save settings" }),
    );

    const puts = callsTo(fetchMock, "PUT", "/api/settings");
    expect(bodyOf(puts[0])).toEqual({ always_hashtags: ["pizza"] });
    expect(await screen.findByText("#pizza")).toBeVisible();
  });

  it("saves what happens to posts missed while the app was off", async () => {
    const fetchMock = routes({
      "PUT /api/settings": () =>
        json({ ...SAVED, post_missed_policy: "skip" } satisfies SettingsView),
    });
    renderPage();
    await screen.findByLabelText("Model");
    const select = screen.getByLabelText(
      "Posts missed while ClipForge was off",
    );
    expect(select).toHaveValue("post_late");

    await userEvent.selectOptions(select, "Skip them");
    await userEvent.click(
      screen.getByRole("button", { name: "Save settings" }),
    );

    const puts = callsTo(fetchMock, "PUT", "/api/settings");
    expect(bodyOf(puts[0])).toEqual({ post_missed_policy: "skip" });
    await waitFor(() => expect(select).toHaveValue("skip"));
  });

  it("removes a saved key with an empty value", async () => {
    const fetchMock = routes({
      "PUT /api/settings": () =>
        json({ ...SAVED, openai_api_key_set: false } satisfies SettingsView),
    });
    renderPage();
    await screen.findByLabelText("Model");
    await userEvent.click(screen.getByRole("radio", { name: /OpenAI/ }));

    await userEvent.click(screen.getByRole("button", { name: "Remove key" }));
    expect(screen.getByText("Will be removed when you save")).toBeVisible();
    await userEvent.click(
      screen.getByRole("button", { name: "Save settings" }),
    );

    const puts = callsTo(fetchMock, "PUT", "/api/settings");
    expect(bodyOf(puts[0])).toEqual({
      llm_provider: "openai",
      openai_api_key: "",
    });
    await waitFor(() =>
      expect(within(llmSection()).getByText("Not set")).toBeVisible(),
    );
  });

  it("shows the problems and sends nothing", async () => {
    const fetchMock = routes();
    renderPage();
    await userEvent.clear(await screen.findByLabelText("Model"));

    await userEvent.click(
      screen.getByRole("button", { name: "Save settings" }),
    );

    expect(screen.getByText("Enter a model name.")).toBeVisible();
    expect(callsTo(fetchMock, "PUT", "/api/settings")).toHaveLength(0);
  });

  it("shows the server's refusal as a toast and keeps the draft", async () => {
    routes({
      "PUT /api/settings": () =>
        json(
          { error: "conflict", message: "llm_model cannot be changed here" },
          409,
        ),
    });
    renderPage();
    await userEvent.type(await screen.findByLabelText("Model"), "x");

    await userEvent.click(
      screen.getByRole("button", { name: "Save settings" }),
    );

    expect(
      await screen.findByText("llm_model cannot be changed here"),
    ).toBeVisible();
    expect(screen.getByLabelText("Model")).toHaveValue("claude-sonnet-5.5x");
  });

  it("tests the connection with the unsaved form values", async () => {
    const fetchMock = routes({
      "POST /api/settings/test-llm": () =>
        json({
          ok: true,
          provider: "ollama",
          model: "llama3",
          message: '{"ok": true}',
        }),
    });
    renderPage();
    await userEvent.click(await screen.findByRole("radio", { name: /Ollama/ }));
    await userEvent.clear(screen.getByLabelText("Model"));
    await userEvent.type(screen.getByLabelText("Model"), "llama3");

    await userEvent.click(
      screen.getByRole("button", { name: "Test connection" }),
    );

    const status = await screen.findByRole("status");
    expect(status).toHaveTextContent(
      'Connected (ollama, llama3): {"ok": true}',
    );
    const posts = callsTo(fetchMock, "POST", "/api/settings/test-llm");
    expect(bodyOf(posts[0])).toEqual({
      llm_provider: "ollama",
      llm_model: "llama3",
    });
    expect(callsTo(fetchMock, "PUT", "/api/settings")).toHaveLength(0);
  });

  it("sets up the Anthropic API with a model from the key's list", async () => {
    const fetchMock = routes({
      "POST /api/settings/models": () =>
        json({ models: ["claude-opus-5-5", "claude-sonnet-5-5"], error: null }),
      "PUT /api/settings": () => json(SAVED),
    });
    renderPage();
    await userEvent.click(
      await screen.findByRole("radio", { name: "Anthropic API" }),
    );
    expect(screen.queryByLabelText("GitHub account")).toBeNull();
    await userEvent.type(screen.getByLabelText("API key"), "sk-ant-new");

    await userEvent.click(screen.getByRole("button", { name: "Load models" }));

    expect(await screen.findByText("2 models available.")).toBeVisible();
    const model = screen.getByRole("combobox", { name: "Model" });
    expect(model).toHaveValue("claude-sonnet-5-5");
    expect(
      [...model.querySelectorAll("option")].map((option) => option.textContent),
    ).toEqual(["claude-opus-5-5", "claude-sonnet-5-5", "Custom…"]);
    const posts = callsTo(fetchMock, "POST", "/api/settings/models");
    expect(bodyOf(posts[posts.length - 1])).toEqual({
      llm_provider: "anthropic",
      anthropic_api_key: "sk-ant-new",
    });

    await userEvent.selectOptions(model, "claude-opus-5-5");
    await userEvent.click(
      screen.getByRole("button", { name: "Save settings" }),
    );
    const puts = callsTo(fetchMock, "PUT", "/api/settings");
    expect(puts.map(bodyOf)).toEqual([
      {
        llm_provider: "anthropic",
        anthropic_model: "claude-opus-5-5",
        anthropic_api_key: "sk-ant-new",
      },
    ]);
  });

  it("picks the Copilot model from the account's list or a custom one", async () => {
    const fetchMock = routes({
      "POST /api/settings/models": () =>
        json({ models: ["claude-sonnet-5.5", "gpt-6-luna"], error: null }),
      "PUT /api/settings": () => json(SAVED),
    });
    renderPage();
    const model = await screen.findByRole("combobox", { name: "Model" });
    expect(model).toHaveValue("claude-sonnet-5.5");
    expect(screen.queryByLabelText("Custom model")).toBeNull();
    expect(
      bodyOf(callsTo(fetchMock, "POST", "/api/settings/models")[0]),
    ).toEqual({});

    await userEvent.selectOptions(model, "Custom…");
    const custom = screen.getByLabelText("Custom model");
    expect(custom).toHaveValue("claude-sonnet-5.5");
    await userEvent.clear(custom);
    await userEvent.type(custom, "gpt-9");
    await userEvent.click(
      screen.getByRole("button", { name: "Save settings" }),
    );

    expect(callsTo(fetchMock, "PUT", "/api/settings").map(bodyOf)).toEqual([
      { llm_model: "gpt-9" },
    ]);
  });

  it("shows a saved model that the list lacks as a custom one", async () => {
    routes({
      "POST /api/settings/models": () =>
        json({ models: ["gpt-6-luna"], error: null }),
    });
    renderPage();

    const model = await screen.findByRole("combobox", { name: "Model" });
    expect(model).toHaveValue("\u0000custom");
    expect(screen.getByLabelText("Custom model")).toHaveValue(
      "claude-sonnet-5.5",
    );
  });

  it("keeps the old model and shows the provider's error when the save is refused", async () => {
    routes({
      "PUT /api/settings": () =>
        json(
          {
            error: "llm_rejected",
            message:
              "copilot did not accept model soclaude; nothing was saved: copilot: HTTP 400: model_not_supported",
          },
          422,
        ),
    });
    renderPage();
    await userEvent.clear(await screen.findByLabelText("Model"));
    await userEvent.type(screen.getByLabelText("Model"), "soclaude");

    await userEvent.click(
      screen.getByRole("button", { name: "Save settings" }),
    );

    expect(await screen.findByText(/model_not_supported/)).toBeVisible();
    expect(screen.getByLabelText("Model")).toHaveValue("soclaude");
    expect(screen.getByRole("button", { name: "Save settings" })).toBeEnabled();
  });

  it("shows why the models could not be listed", async () => {
    routes({
      "POST /api/settings/models": () =>
        json({ models: [], error: "anthropic: HTTP 401: invalid key ***" }),
    });
    renderPage();
    await userEvent.click(
      await screen.findByRole("radio", { name: "Anthropic API" }),
    );

    expect(await screen.findByRole("status")).toHaveTextContent(
      "anthropic: HTTP 401: invalid key ***",
    );
    expect(screen.getByLabelText("Model")).toHaveValue("claude-sonnet-5-5");
  });

  it("tests the Claude subscription and shows the login hint", async () => {
    const fetchMock = routes({
      "POST /api/settings/test-llm": () =>
        json({
          ok: false,
          provider: "claude_code",
          model: "opus",
          message:
            "claude_code: Claude Code is not logged in. Run `claude` in a terminal and log in, then retry.",
        }),
    });
    renderPage();
    await userEvent.click(
      await screen.findByRole("radio", {
        name: "Claude subscription (Claude Code)",
      }),
    );
    expect(screen.getByLabelText("Claude Code program")).toHaveValue("claude");
    expect(screen.queryByLabelText("API key")).toBeNull();
    await userEvent.clear(screen.getByLabelText("Model"));
    await userEvent.type(screen.getByLabelText("Model"), "opus");

    await userEvent.click(
      screen.getByRole("button", { name: "Test connection" }),
    );

    expect(await screen.findByRole("status")).toHaveTextContent(
      "Failed (claude_code, opus): claude_code: Claude Code is not logged in.",
    );
    const posts = callsTo(fetchMock, "POST", "/api/settings/test-llm");
    expect(bodyOf(posts[0])).toEqual({
      llm_provider: "claude_code",
      claude_code_model: "opus",
    });
  });

  it("reports a failed connection test", async () => {
    routes({
      "POST /api/settings/test-llm": () =>
        json({
          ok: false,
          provider: "copilot",
          model: "gpt-4.1",
          message: "401 unauthorized",
        }),
    });
    renderPage();
    await userEvent.click(
      await screen.findByRole("button", { name: "Test connection" }),
    );

    expect(await screen.findByRole("status")).toHaveTextContent(
      "Failed (copilot, gpt-4.1): 401 unauthorized",
    );
  });

  it("shows the transcription engine in use and saves another", async () => {
    const fetchMock = routes({
      "PUT /api/settings": () =>
        json({
          ...SAVED,
          transcribe_backend: "faster_whisper",
          transcribe_backend_active: "faster_whisper",
        } satisfies SettingsView),
    });
    renderPage();
    const select = await screen.findByLabelText("Transcription engine");
    expect(select).toHaveValue("auto");
    expect(
      screen.getByText("Apple GPU (MLX)", { selector: "strong" }),
    ).toBeVisible();

    await userEvent.selectOptions(select, "faster_whisper");
    await userEvent.click(
      screen.getByRole("button", { name: "Save settings" }),
    );

    const puts = callsTo(fetchMock, "PUT", "/api/settings");
    expect(puts.map(bodyOf)).toEqual([
      { transcribe_backend: "faster_whisper" },
    ]);
    expect(
      await screen.findByText("CPU (faster-whisper)", { selector: "strong" }),
    ).toBeVisible();
  });

  it("saves the video encoder picked from the ones ffmpeg has", async () => {
    const fetchMock = routes({
      "PUT /api/settings": () =>
        json({ ...SAVED, video_encoder: "libx264" } satisfies SettingsView),
    });
    renderPage();
    const select = await screen.findByLabelText("Video encoder");
    expect(select).toHaveValue("h264_videotoolbox");
    expect(
      within(select)
        .getAllByRole("option")
        .map((option) => option.textContent),
    ).toEqual(["Hardware (VideoToolbox)", "Software (x264)"]);

    await userEvent.selectOptions(select, "libx264");
    await userEvent.click(
      screen.getByRole("button", { name: "Save settings" }),
    );

    const puts = callsTo(fetchMock, "PUT", "/api/settings");
    expect(puts.map(bodyOf)).toEqual([{ video_encoder: "libx264" }]);
    expect(await screen.findByText("Settings saved.")).toBeVisible();
    expect(screen.getByLabelText("Video encoder")).toHaveValue("libx264");
  });

  it("offers only software encoding when ffmpeg lacks VideoToolbox", async () => {
    routes({
      "GET /api/settings": () =>
        json({
          ...SAVED,
          video_encoder: "libx264",
          video_encoders: ["libx264"],
        } satisfies SettingsView),
    });
    renderPage();

    const select = await screen.findByLabelText("Video encoder");
    expect(select).toHaveValue("libx264");
    expect(
      within(select)
        .getAllByRole("option")
        .map((option) => option.textContent),
    ).toEqual(["Software (x264)"]);
  });
});
