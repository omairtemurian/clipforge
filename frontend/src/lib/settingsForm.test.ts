import { describe, expect, it } from "vitest";
import { SAVED_SETTINGS as SAVED } from "@/testing/mockApi";
import {
  draftOf,
  llmTestBody,
  settingsPatch,
  validateSettings,
} from "./settingsForm";

describe("settingsPatch", () => {
  it("is empty for an untouched draft", () => {
    expect(settingsPatch(draftOf(SAVED), SAVED)).toEqual({});
  });

  it("sends only the fields that changed, trimmed", () => {
    const draft = draftOf(SAVED);
    draft.llm_provider = "ollama";
    draft.text.llm_model = " llama3 ";
    draft.text.ffmpeg_bin = "/usr/bin/ffmpeg";
    expect(settingsPatch(draft, SAVED)).toEqual({
      llm_provider: "ollama",
      llm_model: "llama3",
      ffmpeg_bin: "/usr/bin/ffmpeg",
    });
  });

  it("sends the always-included hashtags only when they changed", () => {
    const draft = draftOf(SAVED);
    expect(settingsPatch(draft, SAVED)).toEqual({});
    draft.always_hashtags = ["pizza", "funny"];
    expect(settingsPatch(draft, SAVED)).toEqual({
      always_hashtags: ["pizza", "funny"],
    });
  });

  it("sends a changed missed-posts policy", () => {
    const draft = draftOf(SAVED);
    draft.post_missed_policy = "skip";
    expect(settingsPatch(draft, SAVED)).toEqual({ post_missed_policy: "skip" });
  });

  it("sends a changed video encoder", () => {
    const draft = draftOf(SAVED);
    draft.video_encoder = "libx264";
    expect(settingsPatch(draft, SAVED)).toEqual({ video_encoder: "libx264" });
  });

  it("sends a changed transcription backend", () => {
    const draft = draftOf(SAVED);
    draft.transcribe_backend = "mlx";
    expect(settingsPatch(draft, SAVED)).toEqual({ transcribe_backend: "mlx" });
  });

  it("sends a typed key, and an empty one to clear it", () => {
    const draft = draftOf(SAVED);
    draft.keys.openai_api_key = { typed: "sk-new", clear: false };
    draft.keys.github_copilot_token = { typed: "", clear: true };
    expect(settingsPatch(draft, SAVED)).toEqual({
      openai_api_key: "sk-new",
      github_copilot_token: "",
    });
  });

  it("keeps a saved key when nothing is typed", () => {
    const draft = draftOf(SAVED);
    draft.keys.openai_api_key = { typed: "  ", clear: false };
    expect(settingsPatch(draft, SAVED)).toEqual({});
  });
});

describe("llmTestBody", () => {
  it("holds the model choice and its key, not the other settings", () => {
    const draft = draftOf(SAVED);
    draft.llm_provider = "openai";
    draft.text.llm_model = "gpt-5";
    draft.text.whisper_model = "medium";
    draft.keys.openai_api_key = { typed: "sk-try", clear: false };
    expect(llmTestBody(draft, SAVED)).toEqual({
      llm_provider: "openai",
      llm_model: "gpt-5",
      openai_api_key: "sk-try",
    });
  });

  it("tries a changed Copilot account", () => {
    const draft = draftOf(SAVED);
    draft.text.copilot_account = " omairtemurian ";
    expect(llmTestBody(draft, SAVED)).toEqual({
      copilot_account: "omairtemurian",
    });
  });

  it("tries the Anthropic provider with its key, model and URL", () => {
    const draft = draftOf(SAVED);
    draft.llm_provider = "anthropic";
    draft.text.anthropic_model = "claude-opus-5-5";
    draft.text.anthropic_base_url = "https://proxy.example";
    draft.keys.anthropic_api_key = { typed: " sk-ant-try ", clear: false };
    expect(llmTestBody(draft, SAVED)).toEqual({
      llm_provider: "anthropic",
      anthropic_model: "claude-opus-5-5",
      anthropic_base_url: "https://proxy.example",
      anthropic_api_key: "sk-ant-try",
    });
  });

  it("tries the Claude subscription with its model and program", () => {
    const draft = draftOf(SAVED);
    draft.llm_provider = "claude_code";
    draft.text.claude_code_model = " opus ";
    draft.text.claude_code_bin = "/opt/homebrew/bin/claude";
    expect(llmTestBody(draft, SAVED)).toEqual({
      llm_provider: "claude_code",
      claude_code_model: "opus",
      claude_code_bin: "/opt/homebrew/bin/claude",
    });
  });
});

describe("validateSettings", () => {
  it("accepts the saved settings", () => {
    expect(validateSettings(draftOf(SAVED))).toEqual({});
  });

  it("flags empty required fields and non-http URLs", () => {
    const draft = draftOf(SAVED);
    draft.text.llm_model = " ";
    draft.text.copilot_account = "";
    draft.text.ollama_host = "localhost:11434";
    draft.text.anthropic_model = "";
    draft.text.anthropic_base_url = "api.anthropic.com";
    draft.text.claude_code_model = "";
    expect(validateSettings(draft)).toEqual({
      llm_model: "Enter a model name.",
      ollama_host: "Enter an http(s) URL.",
      anthropic_model: "Enter a model name.",
      anthropic_base_url: "Enter an http(s) URL.",
      claude_code_model: "Enter a model name.",
    });
  });
});
