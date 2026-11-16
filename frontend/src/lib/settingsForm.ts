import type { SettingsUpdate, SettingsView } from "@/api/types";

export type LlmProvider = SettingsView["llm_provider"];
export type VideoEncoder = SettingsView["video_encoder"];
export type TranscribeBackend = SettingsView["transcribe_backend"];
export type MissedPolicy = SettingsView["post_missed_policy"];

/** The name the Settings page shows for the backend that transcribes. */
export function backendLabel(backend: "faster_whisper" | "mlx"): string {
  return backend === "mlx" ? "Apple GPU (MLX)" : "CPU (faster-whisper)";
}

/** The text fields of the Settings page; a key is only ever typed here. */
export type TextField =
  | "llm_model"
  | "openai_base_url"
  | "ollama_host"
  | "copilot_account"
  | "anthropic_base_url"
  | "anthropic_model"
  | "claude_code_bin"
  | "claude_code_model"
  | "whisper_model"
  | "credit_template"
  | "models_dir"
  | "ffmpeg_bin"
  | "ffprobe_bin"
  | "ytdlp_cookies_from_browser"
  | "ytdlp_cookies_file";

export type KeyField =
  "openai_api_key" | "github_copilot_token" | "anthropic_api_key";

export interface KeyDraft {
  /** What the user typed; empty keeps the saved key. */
  typed: string;
  /** Remove the saved key. */
  clear: boolean;
}

export interface SettingsDraft {
  llm_provider: LlmProvider;
  video_encoder: VideoEncoder;
  transcribe_backend: TranscribeBackend;
  always_hashtags: string[];
  post_missed_policy: MissedPolicy;
  text: Record<TextField, string>;
  keys: Record<KeyField, KeyDraft>;
}

export const TEXT_FIELDS: TextField[] = [
  "llm_model",
  "openai_base_url",
  "ollama_host",
  "copilot_account",
  "anthropic_base_url",
  "anthropic_model",
  "claude_code_bin",
  "claude_code_model",
  "whisper_model",
  "credit_template",
  "models_dir",
  "ffmpeg_bin",
  "ffprobe_bin",
  "ytdlp_cookies_from_browser",
  "ytdlp_cookies_file",
];

export const KEY_FIELDS: KeyField[] = [
  "openai_api_key",
  "github_copilot_token",
  "anthropic_api_key",
];

/** Fields that the server rejects when empty (the tool paths, cookies and
 * keys may be empty). */
const REQUIRED: Partial<Record<TextField, string>> = {
  llm_model: "Enter a model name.",
  anthropic_model: "Enter a model name.",
  claude_code_bin: "Enter the Claude Code program.",
  claude_code_model: "Enter a model name.",
  whisper_model: "Enter a whisper model.",
  credit_template: "Enter a credit template.",
  models_dir: "Enter a models folder.",
};

const URLS: Partial<Record<TextField, string>> = {
  openai_base_url: "Enter an http(s) URL.",
  ollama_host: "Enter an http(s) URL.",
  anthropic_base_url: "Enter an http(s) URL.",
};

/** The draft that shows the saved settings with no key typed. */
export function draftOf(view: SettingsView): SettingsDraft {
  const text = Object.fromEntries(
    TEXT_FIELDS.map((field) => [field, view[field]]),
  ) as Record<TextField, string>;
  const none = { typed: "", clear: false };
  return {
    llm_provider: view.llm_provider,
    video_encoder: view.video_encoder,
    transcribe_backend: view.transcribe_backend,
    always_hashtags: view.always_hashtags,
    post_missed_policy: view.post_missed_policy,
    text,
    keys: {
      openai_api_key: none,
      github_copilot_token: none,
      anthropic_api_key: none,
    },
  };
}

/**
 * The PUT body of a draft: only what differs from the saved settings. A key
 * is sent when one was typed, or as "" when the user cleared it.
 */
export function settingsPatch(
  draft: SettingsDraft,
  saved: SettingsView,
): SettingsUpdate {
  const patch: SettingsUpdate = {};
  if (draft.llm_provider !== saved.llm_provider) {
    patch.llm_provider = draft.llm_provider;
  }
  if (draft.video_encoder !== saved.video_encoder) {
    patch.video_encoder = draft.video_encoder;
  }
  if (draft.transcribe_backend !== saved.transcribe_backend) {
    patch.transcribe_backend = draft.transcribe_backend;
  }
  if (draft.always_hashtags.join() !== saved.always_hashtags.join()) {
    patch.always_hashtags = draft.always_hashtags;
  }
  if (draft.post_missed_policy !== saved.post_missed_policy) {
    patch.post_missed_policy = draft.post_missed_policy;
  }
  for (const field of TEXT_FIELDS) {
    const value = draft.text[field].trim();
    if (value !== saved[field]) patch[field] = value;
  }
  for (const field of KEY_FIELDS) {
    const { typed, clear } = draft.keys[field];
    if (typed.trim()) patch[field] = typed.trim();
    else if (clear) patch[field] = "";
  }
  return patch;
}

/** The body of "Test connection": the draft's LLM choice, which is tried
 * without being saved. */
export function llmTestBody(
  draft: SettingsDraft,
  saved: SettingsView,
): SettingsUpdate {
  const llm: (keyof SettingsUpdate)[] = [
    "llm_provider",
    "llm_model",
    "openai_base_url",
    "ollama_host",
    "openai_api_key",
    "github_copilot_token",
    "copilot_account",
    "anthropic_api_key",
    "anthropic_base_url",
    "anthropic_model",
    "claude_code_bin",
    "claude_code_model",
  ];
  const patch = settingsPatch(draft, saved);
  return Object.fromEntries(
    Object.entries(patch).filter(([name]) =>
      llm.includes(name as keyof SettingsUpdate),
    ),
  );
}

/** The problems of a draft by field, for the fields that cannot be empty or
 * must be a URL. */
export function validateSettings(
  draft: SettingsDraft,
): Partial<Record<TextField, string>> {
  const problems: Partial<Record<TextField, string>> = {};
  for (const [field, message] of Object.entries(REQUIRED)) {
    if (!draft.text[field as TextField].trim()) {
      problems[field as TextField] = message;
    }
  }
  for (const [field, message] of Object.entries(URLS)) {
    if (!/^https?:\/\/\S+$/.test(draft.text[field as TextField].trim())) {
      problems[field as TextField] = message;
    }
  }
  return problems;
}
