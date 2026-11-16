import { vi } from "vitest";
import { NO_STYLE } from "@/lib/clipLook";
import { DEFAULT_FRAMING } from "@/lib/cropFrame";
import type {
  CaptionTemplateInfo,
  Clip,
  EngineStatus,
  Job,
  ProcessingSettings,
  Timeline,
  Project,
  ReframePresetInfo,
  SettingsView,
  UsageSummary,
} from "@/api/types";

export type Handler = (
  url: string,
  init?: RequestInit,
) => Response | Promise<Response>;

/** A JSON response. */
export function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status });
}

/** Replace fetch with handler; returns the mock to inspect its calls. */
export function mockApi(handler: Handler) {
  const fetchMock = vi.fn((url: string, init?: RequestInit) =>
    Promise.resolve(handler(url, init)),
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

/**
 * Replace fetch with a table of "METHOD /api/path" -> handler; any other
 * request gets a 404 {error, message} like the real API.
 */
export function mockRoutes(routes: Record<string, Handler>) {
  return mockApi((url, init) => {
    const route = routes[`${init?.method ?? "GET"} ${url}`];
    return route
      ? route(url, init)
      : json({ error: "not_found", message: `no route ${url}` }, 404);
  });
}

/** The calls of fetchMock with the given method and URL. */
export function callsTo(
  fetchMock: ReturnType<typeof mockApi>,
  method: string,
  url: string,
) {
  return fetchMock.mock.calls.filter(
    ([callUrl, init]) => callUrl === url && (init?.method ?? "GET") === method,
  );
}

/** A project as the API returns it. */
export function project(overrides: Partial<Project>): Project {
  return {
    id: 1,
    source_url: "https://youtu.be/a",
    source_path: "",
    title: "First talk",
    duration: 60,
    thumbnail_path: "/work/thumb.jpg",
    settings: {} as Project["settings"],
    status: "done",
    created_at: "2026-10-30T12:00:00",
    source_rights: null,
    credit_line: "",
    campaign_id: null,
    source_published_at: null,
    result_set: 1,
    overall_progress: 0,
    eta_seconds: null,
    opened_at: "2026-10-30T12:05:00",
    archived_at: null,
    rights_set: false,
    fresh_upload: false,
    ...overrides,
  };
}

/** A process job of project 1 as the API returns it (queued, no step). */
export function job(overrides: Partial<Job> = {}): Job {
  return {
    id: 7,
    project_id: 1,
    clip_id: null,
    kind: "process",
    step: "",
    progress: 0,
    status: "queued",
    error: null,
    log_path: "",
    priority: 0,
    attempts: 0,
    overall_progress: 0,
    eta_seconds: null,
    ...overrides,
  };
}

/** GET /processing-defaults with the server's default of 10 clips. */
export const DEFAULTS: ProcessingSettings = {
  genre: "auto",
  length_presets: ["auto"],
  custom_length_min_s: null,
  custom_length_max_s: null,
  timeframe_start: null,
  timeframe_end: null,
  num_clips: 10,
  aspect: "9:16",
  caption_template: "karaoke_bold",
  caption_colors: {
    primary_color: null,
    highlight_color: null,
    emphasis_color: null,
  },
  keyword_prompt: null,
  remove_fillers: false,
  auto_cut: true,
  auto_cut_min_pause_s: 0.5,
  auto_zoom: true,
  auto_headline: true,
  auto_color: false,
  captions: true,
  language: null,
  subtitles_id: null,
  clipping: "ai",
  clip_anything: false,
  search_terms: [],
  brand_template_id: null,
  reframe_preset: null,
  default_layout: "auto",
  zoom_out_moments: "balanced",
  camera_motion: "calm",
};

/** GET /caption-templates entries (only the fields the UI reads matter). */
export function captionTemplate(name: string): CaptionTemplateInfo {
  return styledTemplate(name, {
    primary_color: "#ffffff",
    highlight_color: "#ffd23f",
    emphasis_color: "#ff6b35",
  });
}

/** A GET /caption-templates entry whose template has the given fields. */
export function styledTemplate(
  name: string,
  template: Partial<CaptionTemplateInfo["template"]>,
): CaptionTemplateInfo {
  return {
    name,
    template: template as CaptionTemplateInfo["template"],
    preview_url: `/api/caption-templates/${name}/preview.png`,
  };
}

/** The timeline of a clip that plays the source from start to end. */
export function timelineOf(start: number, end: number): Timeline {
  const item = { id: "video-0", kind: "source" as const, asset_id: null };
  return {
    video: [{ ...item, start, end, props: {} }],
    broll: [],
    overlays: [],
    text: [],
    music: [],
    sfx: [],
    voiceover: [],
  };
}

/** A clip as the API returns it: one segment from start to end (10-40 s
 * unless overrides set them). */
export function clip(overrides: Partial<Clip> = {}): Clip {
  const start = overrides.start ?? 10;
  const end = overrides.end ?? 40;
  return {
    id: 1,
    project_id: 1,
    segments: [[start, end]],
    tracks: timelineOf(start, end),
    start,
    end,
    title: "Pizza night",
    hook_text: "He ate it all",
    description: "A man and a whole pizza.",
    hashtags: ["pizza", "funny", "standup"],
    emphasis_words: [],
    reason: "A clean setup and a big laugh.",
    scores: {
      overall: 85,
      hook: 90,
      flow: 80,
      value: 70,
      trend: 60,
      laugh: 0.5,
      energy: 0.4,
    },
    layout: "fill",
    caption_template: "karaoke_bold",
    caption_overrides: [],
    caption_style: NO_STYLE,
    crop_offset: 0,
    framing: DEFAULT_FRAMING,
    auto_cut: false,
    auto_zoom: false,
    zoom_keyframes: [],
    scene_reframes: [],
    auto_color: false,
    show_captions: true,
    transitions: { auto: null, sections: [] },
    hook: null,
    enhance: 0,
    parent_clip_id: null,
    variant: "original",
    result_set: 1,
    cut_ranges: [],
    status: "candidate",
    output_path: null,
    ...overrides,
  };
}

/** A clip with an overall score. */
export function scored(
  id: number,
  overall: number,
  title = `Clip ${id}`,
): Clip {
  const base = clip();
  return clip({
    id,
    title,
    hook_text: "",
    description: "",
    hashtags: [],
    scores: { ...base.scores, overall },
  });
}

/** GET /settings as the server returns it (no key is ever included). */
export const SAVED_SETTINGS: SettingsView = {
  llm_provider: "copilot",
  always_hashtags: [],
  post_missed_policy: "post_late",
  llm_model: "claude-sonnet-5.5",
  openai_base_url: "https://api.openai.com/v1",
  ollama_host: "http://localhost:11434",
  openai_api_key_set: true,
  github_copilot_token_set: false,
  copilot_account: "",
  anthropic_api_key_set: false,
  anthropic_base_url: "https://api.anthropic.com",
  anthropic_model: "claude-sonnet-5-5",
  claude_code_bin: "claude",
  claude_code_model: "sonnet",
  whisper_model: "small",
  transcribe_backend: "auto",
  transcribe_backend_active: "mlx",
  credit_template: "Credit: {channel}",
  models_dir: "models",
  ffmpeg_bin: "",
  ffprobe_bin: "",
  video_encoder: "h264_videotoolbox",
  video_encoders: ["libx264", "h264_videotoolbox"],
  ytdlp_cookies_from_browser: "",
  ytdlp_cookies_file: "",
  usage_cap_compute_hours: 0,
  usage_cap_llm_tokens: 0,
  usage_cap_api_calls: 0,
  smtp_host: "",
  smtp_port: 587,
  smtp_user: "",
  smtp_password_set: false,
  smtp_from: "",
  notify_email_to: "",
  desktop_notifications: false,
  quota_warn_percent: 80,
  digest_time: "08:00",
  data_dir: "data",
};

/** A GET /usage answer for the month: the given totals (seconds of compute,
 * tokens, calls) and no caps, unless a kind has one. */
export function usageSummary(
  totals: Partial<Record<"compute" | "llm_tokens" | "api_calls", number>> = {},
  caps: Partial<Record<"compute" | "llm_tokens" | "api_calls", number>> = {},
): UsageSummary {
  const kinds = (["compute", "llm_tokens", "api_calls"] as const).map(
    (kind) => ({
      kind,
      units: totals[kind] ?? 0,
      cost_usd: null,
      cap: caps[kind] ?? null,
      exceeded: kind in caps && (totals[kind] ?? 0) >= (caps[kind] ?? 0),
    }),
  );
  return { month: "2026-10", kinds, projects: [] };
}

/** A GET /engines entry: installed (with a version) or not (with a reason). */
export function engineStatus(
  name: string,
  installed: boolean,
  overrides: Partial<EngineStatus> = {},
): EngineStatus {
  return {
    name,
    label: `Engine ${name}`,
    installed,
    version: installed ? "1.0" : null,
    error: installed ? null : `${name} is not installed`,
    doc_anchor: `engine-${name}`,
    ...overrides,
  };
}

/** GET /reframe-presets entries: podcast-2 and gaming. */
export const REFRAME_PRESETS: ReframePresetInfo[] = [
  {
    name: "podcast-2",
    label: "Podcast (two speakers)",
    description: "Splits the frame when two people talk.",
    layout: null,
    split_share: 0.4,
    camera_motion: "calm",
    objects: false,
  },
  {
    name: "gaming",
    label: "Gaming",
    description: "Fits the whole screen.",
    layout: "fit",
    split_share: 1,
    camera_motion: "calm",
    objects: false,
  },
];
