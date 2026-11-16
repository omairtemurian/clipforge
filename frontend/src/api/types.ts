/* eslint-disable */
/**
 * GENERATED FILE - DO NOT EDIT BY HAND.
 * Source: the Pydantic models of backend/clipforge (models.py and the API).
 * Regenerate with: uv run python scripts/gen_types.py
 */

/**
 * One track per audio event kind: the content of audio_events.json.
 */
export type AudioEventList = AudioEventTrack[];
/**
 * Signal events as a JSON array: the content of signals.json (SPEC 6.3).
 */
export type SignalList = SignalEvent[];

/**
 * The platform's sign-in page that connects an account.
 */
export interface AccountConnect {
  authorize_url: string;
}
/**
 * The body of PUT /accounts/{id}/hashtags: the hashtags (without "#")
 * that every generated post to the account carries, besides the global
 * always_hashtags setting and the campaign's required hashtags.
 */
export interface AccountHashtags {
  /**
   * @maxItems 30
   */
  always_hashtags: string[];
}
/**
 * What an AI agent needs to reach this ClipForge (Settings -> AI agents &
 * API): api_url is this app's address (CLIPFORGE_URL of the MCP server),
 * project_dir the checkout with the clipforge-mcp command, mcp_command +
 * mcp_args start that MCP server, docs_url is the REST API's Swagger UI.
 */
export interface AgentSetup {
  api_url: string;
  project_dir: string;
  mcp_command: string;
  mcp_args: string[];
  docs_url: string;
}
/**
 * An API key of the public REST API /api/v1 (SPEC-v2 3.14, 4). The key
 * itself is shown once, when it is made (ApiKeyCreated); only its hash is
 * stored. prefix is its first characters, to tell keys apart;
 * last_used_at is when a request last came with it (None: never).
 */
export interface ApiKey {
  id: number;
  name: string;
  prefix: string;
  created_at: string;
  last_used_at: string | null;
}
/**
 * Body of POST /api-keys: the name the owner gives the new key.
 */
export interface ApiKeyCreate {
  name: string;
}
/**
 * A key just made: key is the secret itself, shown this once.
 */
export interface ApiKeyCreated {
  id: number;
  name: string;
  prefix: string;
  created_at: string;
  last_used_at: string | null;
  key: string;
}
/**
 * A file in the asset library with its license (SPEC-v2 1.3, 4). The
 * fields after tags describe an audio asset (SPEC-v3 5): its tempo (bpm),
 * musical key, integrated loudness, energy over time (one value per
 * second, 0 to 1), category (whoosh, impact, riser, ...), mood and when it
 * was downloaded; they are None for an asset that was not analyzed or is
 * not audio.
 */
export interface Asset {
  id: number;
  kind: "video" | "image" | "audio" | "font" | "logo" | "music" | "sfx";
  path: string;
  license: string;
  attribution: string;
  source_url: string | null;
  tags: string[];
  bpm: number | null;
  key: string | null;
  loudness_lufs: number | null;
  energy_curve: number[] | null;
  category: string | null;
  mood: string | null;
  downloaded_at: string | null;
}
/**
 * What YAMNet heard of one kind of non-speech audio event, per second.
 *
 * scores[i] (0..1) is the highest score of the kind in the second that
 * starts at start + i, in source seconds.
 */
export interface AudioEventTrack {
  kind: "laugh" | "applause" | "cheer" | "music";
  start: number;
  scores: number[];
}
/**
 * The props of a music, sound effect or voiceover item: the asset from
 * offset seconds, at volume (1: as recorded), mixed with the clip's
 * sound.
 */
export interface AudioProps {
  volume: number;
  offset: number;
}
/**
 * The body of POST /clips/{id}/auto-sfx: how many sounds to place at
 * most.
 */
export interface AutoSfxOptions {
  max_items: number;
}
/**
 * The body of PUT /autopilot/pause: pause (true) or resume (false) the
 * autopilot of every campaign.
 */
export interface AutopilotPauseUpdate {
  paused: boolean;
}
/**
 * The autopilot settings of campaign campaign_id (a campaign that was
 * never set up has the defaults: off).
 */
export interface AutopilotSettings {
  enabled: boolean;
  max_clips_per_source: number;
  slots: ScheduleRules | null;
  max_posts_per_day: number;
  draft_ttl_days: number;
  /**
   * @maxItems 50
   */
  account_ids: number[];
  min_clip_s: number | null;
  max_clip_s: number | null;
  caption_template: string | null;
  brand_template_id: number | null;
  proedit_enabled: boolean;
  proedit_preset:
    | "clean_pro"
    | "dark_edit"
    | "phonk_edit"
    | "cinematic"
    | "skull_moment"
    | "glitch";
  proedit_max_intensity: "clean" | "standard" | "pro" | "extreme";
  campaign_id: number;
}
/**
 * The bulk scheduler's rules (SPEC-v2 3.10): the posting days and the
 * times of day of the slots, in the IANA timezone (e.g. "Europe/Zurich").
 * Each posting day gets posts_per_day slots, the earliest of times
 * (default: all of them); skip_days have no slots; the first posting day
 * is start_date (default: today). A time that the clocks skip (spring
 * forward) is moved forward by the gap; a time that happens twice (fall
 * back) is used once, the first time.
 */
export interface ScheduleRules {
  timezone: string;
  /**
   * @minItems 1
   * @maxItems 24
   */
  times: [string, ...string[]];
  posts_per_day: number | null;
  skip_days: ("mon" | "tue" | "wed" | "thu" | "fri" | "sat" | "sun")[];
  start_date: string | null;
}
/**
 * The body of PUT /campaigns/{id}/autopilot (SPEC-v2 3.19): how the
 * autopilot of a campaign works. It only ever makes drafts for the owner
 * to approve; it never posts, schedules or submits by itself.
 *
 * enabled turns it on; max_clips_per_source is how many clips of a new
 * source video may become drafts; min_clip_s/max_clip_s (seconds, None:
 * the campaign's own range), caption_template (None: the campaign's) and
 * brand_template_id (None: the default look) are what its projects are
 * made with; slots are the posting slots (None: the posting rules the
 * owner gives when approving) and max_posts_per_day is the most posts a
 * day on one account (hard cap 5), so a day of slots may not have more
 * times; draft_ttl_days is how many days a draft waits before it expires;
 * account_ids are the owner's accounts that approved drafts go to.
 */
export interface AutopilotSettingsUpdate {
  enabled: boolean;
  max_clips_per_source: number;
  slots: ScheduleRules | null;
  max_posts_per_day: number;
  draft_ttl_days: number;
  /**
   * @maxItems 50
   */
  account_ids: number[];
  min_clip_s: number | null;
  max_clip_s: number | null;
  caption_template: string | null;
  brand_template_id: number | null;
  proedit_enabled: boolean;
  proedit_preset:
    | "clean_pro"
    | "dark_edit"
    | "phonk_edit"
    | "cinematic"
    | "skull_moment"
    | "glitch";
  proedit_max_intensity: "clean" | "standard" | "pro" | "extreme";
}
/**
 * GET /autopilot/status: whether the owner paused every autopilot (since
 * paused_at), and the campaigns whose autopilot is on but stopped.
 */
export interface AutopilotStatus {
  paused: boolean;
  paused_at: string | null;
  stops: AutopilotStop[];
}
/**
 * The autopilot of campaign campaign_id is on but stopped for reason;
 * detail says what the owner can do about it.
 */
export interface AutopilotStop {
  campaign_id: number;
  reason:
    | "paused"
    | "permission_missing"
    | "campaign_inactive"
    | "campaign_ended"
    | "daily_quota";
  detail: string;
}
/**
 * A bad take that the LLM finds in a clip: the numbers of its first and
 * last word in the numbered words of the prompt (from 0).
 */
export interface BadTakePick {
  first: number;
  last: number;
}
/**
 * The LLM's reply with the bad takes of a clip (none if it has none).
 */
export interface BadTakesReply {
  /**
   * @maxItems 20
   */
  takes: BadTakePick[];
}
/**
 * Branding applied to rendered clips.
 */
export interface BrandTemplate {
  id: number;
  name: string;
  logo_path: string;
  logo_position: "tl" | "tr" | "bl" | "br";
  logo_opacity: number;
  font: string;
  primary_color: string;
  intro_path: string | null;
  outro_path: string | null;
}
/**
 * The body of POST /clips/{id}/broll: put source on the clip's B-roll
 * track from start to end seconds of the rendered clip (cut short if the
 * video is shorter) as a full-screen cutaway or a picture-in-picture
 * (x, y, width: BrollProps).
 */
export interface BrollInsert {
  stock: StockClip | null;
  asset_id: number | null;
  start: number;
  end: number;
  mode: "cutaway" | "pip";
  x: number;
  y: number;
  width: number;
}
/**
 * A stock video found by a provider (SPEC-v2 3.6) that can be downloaded
 * as B-roll: provider_id is the provider's own id, preview_url a still or
 * clip for showing results, download_url the file that gets stored (the
 * best fit for the requested size). license and attribution are what the
 * asset keeps; creator_url is None if the provider has no profile page.
 */
export interface StockClip {
  provider: "pexels" | "pixabay";
  provider_id: string;
  page_url: string;
  preview_url: string | null;
  download_url: string;
  width: number;
  height: number;
  duration_s: number;
  creator: string;
  creator_url: string | null;
  tags: string[];
  license: string;
  attribution: string;
}
/**
 * A sentence of a clip that the LLM wants B-roll on: its number in the
 * numbered sentences of the prompt (from 0) and the words to search stock
 * video with.
 */
export interface BrollPick {
  sentence: number;
  /**
   * @minItems 1
   * @maxItems 4
   */
  keywords: [string, ...string[]];
}
/**
 * The props of a B-roll item: a "cutaway" asset fills the frame
 * (scaled to cover it, centered); a "pip" (picture-in-picture) asset is
 * width times the frame's width wide, centered at (x, y) in fractions of
 * the frame. A video asset plays from offset seconds, muted.
 */
export interface BrollProps {
  offset: number;
  mode: "cutaway" | "pip";
  x: number;
  y: number;
  width: number;
}
/**
 * The LLM's reply with the B-roll spots of a clip (none if it needs
 * none).
 */
export interface BrollReply {
  /**
   * @maxItems 10
   */
  spots: BrollPick[];
}
/**
 * What a B-roll item plays: a stock video found by a search (stock,
 * downloaded into the asset library) or a video or image of the asset
 * library (asset_id); exactly one of them.
 */
export interface BrollSource {
  stock: StockClip | null;
  asset_id: number | null;
}
/**
 * A spot of a clip for B-roll, to review: sentence (its number) whose
 * text is said from start to end seconds of the rendered clip (the times a
 * B-roll item there gets), the LLM's keywords, query (what was searched)
 * and the stock videos found (results), or error if the search failed.
 */
export interface BrollSpot {
  sentence: number;
  text: string;
  start: number;
  end: number;
  keywords: string[];
  query: string;
  results: StockClip[];
  error: string | null;
}
/**
 * The body of POST /clips/{id}/broll/spots: how many spots to find at
 * most, how the B-roll will show (it picks the shape of the stock videos
 * found: the clip's for a cutaway, landscape for picture-in-picture) and
 * the stock provider to search (None: the first one with an API key).
 */
export interface BrollSpotsOptions {
  max_spots: number;
  mode: "cutaway" | "pip";
  provider: ("pexels" | "pixabay") | null;
}
/**
 * The body of POST /posts/bulk-schedule: post every clip to every
 * target account, each in the account's next free slot of rules; queue
 * publishes them (human only), else they stay drafts with their time.
 */
export interface BulkSchedule {
  /**
   * @minItems 1
   * @maxItems 200
   */
  clip_ids: [number, ...number[]];
  /**
   * @minItems 1
   * @maxItems 50
   */
  targets: [PostTarget, ...PostTarget[]];
  rules: ScheduleRules;
  queue: boolean;
}
/**
 * An account to post a clip to, with what the post says there.
 */
export interface PostTarget {
  account_id: number;
  text: PostText;
}
/**
 * What one post says on its platform (SPEC-v2 3.10), turned into the
 * platform's payload by clipforge.post_payload. A field left None takes
 * the clip's own (title, description, hashtags). caption is the post's
 * text (YouTube/Facebook: the description; TikTok/Instagram: the caption,
 * which also carries the title); link (the full video) and the hashtags
 * go after it. privacy is a value of the platform (YouTube public /
 * unlisted / private, TikTok's privacy levels; Instagram and Facebook
 * publish publicly). collaborators are only for the platforms whose API
 * takes them (Instagram usernames, Facebook Page ids). options are the
 * platform's other settings (e.g. made_for_kids, allow_comment).
 */
export interface PostText {
  title: string | null;
  caption: string | null;
  hashtags: string[] | null;
  link: string | null;
  privacy: string | null;
  /**
   * @maxItems 10
   */
  collaborators: string[];
  options: {
    [k: string]: unknown;
  };
}
/**
 * The body of PUT /projects/{id}/camera-motion: the camera motion to
 * save for the project and apply to its clips' crop plans.
 */
export interface CameraMotionRequest {
  camera_motion: "calm" | "normal" | "fast";
}
/**
 * The answer to PUT /projects/{id}/camera-motion: the project with the
 * saved camera motion and the ids of the clips whose crop plans were
 * tracked again (render them to apply the change).
 */
export interface CameraMotionResult {
  project: Project;
  clip_ids: number[];
}
/**
 * A source video and the settings used to process it.
 */
export interface Project {
  id: number;
  source_url: string | null;
  source_path: string;
  title: string;
  duration: number;
  thumbnail_path: string;
  settings: ProcessingSettings;
  status: "queued" | "running" | "done" | "failed";
  created_at: string;
  source_rights:
    ("own" | "permission" | "cc_by" | "public_domain" | "other") | null;
  credit_line: string;
  campaign_id: number | null;
  source_published_at: string | null;
  result_set: number;
  overall_progress: number;
  eta_seconds: number | null;
  opened_at: string | null;
  archived_at: string | null;
  /**
   * Whether the source rights are set; publishing needs them (read-only).
   */
  rights_set: boolean;
  /**
   * Whether this is a campaign project of a source published within
   * FRESH_UPLOAD_HOURS (the "fresh upload" badge; read-only).
   */
  fresh_upload: boolean;
}
/**
 * Options chosen for processing one project.
 */
export interface ProcessingSettings {
  genre:
    | "auto"
    | "comedy"
    | "sports_commentary"
    | "faith"
    | "news"
    | "vlog"
    | "gaming"
    | "podcast"
    | "talk"
    | "interview"
    | "other";
  /**
   * @minItems 1
   */
  length_presets: [
    (
      | "auto"
      | "lt30"
      | "0_60"
      | "30_60"
      | "60_90"
      | "60_180"
      | "90_180"
      | "180_300"
      | "300_600"
      | "600_900"
      | "custom"
    ),
    ...(
      | "auto"
      | "lt30"
      | "0_60"
      | "30_60"
      | "60_90"
      | "60_180"
      | "90_180"
      | "180_300"
      | "300_600"
      | "600_900"
      | "custom"
    )[],
  ];
  custom_length_min_s: number | null;
  custom_length_max_s: number | null;
  timeframe_start: number | null;
  timeframe_end: number | null;
  num_clips: number;
  aspect: string;
  caption_template: string;
  caption_colors: CaptionColors;
  keyword_prompt: string | null;
  remove_fillers: boolean;
  auto_cut: boolean;
  auto_cut_min_pause_s: number;
  auto_zoom: boolean;
  auto_headline: boolean;
  auto_color: boolean;
  captions: boolean;
  language: string | null;
  subtitles_id: string | null;
  clipping: "ai" | "captions_only" | "keyword_search";
  clip_anything: boolean;
  /**
   * @maxItems 20
   */
  search_terms: string[];
  brand_template_id: number | null;
  reframe_preset: ("podcast-2" | "standup" | "gaming" | "vlog") | null;
  default_layout:
    | "auto"
    | "dynamic"
    | "fill"
    | "fit"
    | "split"
    | "grid"
    | "pip"
    | "screenshare"
    | "gameplay"
    | "square_blur";
  zoom_out_moments: "off" | "subtle" | "balanced" | "frequent";
  camera_motion: "calm" | "normal" | "fast";
}
/**
 * The caption colors that a processing preset gives the clips of a
 * project over any caption template (None keeps the template's): the
 * words (primary_color), the spoken word (highlight_color) and the
 * emphasis words (emphasis_color).
 */
export interface CaptionColors {
  primary_color: string | null;
  highlight_color: string | null;
  emphasis_color: string | null;
}
/**
 * A clipping campaign (SPEC-v2 3.18). The server sets
 * permission_checked_at when the permission source URL or the screenshot
 * (an Asset) is saved; permission_complete is true once the URL, the
 * screenshot and the date are all there: publishing for a project of the
 * campaign is blocked before (read-only).
 */
export interface Campaign {
  id: number;
  permission_screenshot_asset_id: number | null;
  permission_checked_at: string | null;
  name: string;
  creator_name: string;
  /**
   * @maxItems 50
   */
  source_channel_urls: string[];
  platform_board: "whop" | "direct" | "other";
  campaign_url: string | null;
  permission_source_url: string | null;
  badge: "open" | "register_first" | "apply_first" | "paid";
  rate_per_1k_usd: number | null;
  budget_note: string;
  allowed_platforms: ("youtube" | "tiktok" | "instagram")[];
  /**
   * @maxItems 30
   */
  required_hashtags: string[];
  required_credit_line: string;
  /**
   * @maxItems 30
   */
  required_tags_mentions: string[];
  min_duration_s: number | null;
  max_duration_s: number | null;
  banned_content_notes: string;
  monetization_allowed_elsewhere: boolean | null;
  submission_instructions: string;
  status: "active" | "paused" | "ended";
  notes: string;
  end_date: string | null;
  caption_template: string | null;
  allow_heavy_edits: "true" | "false" | "unknown";
  /**
   * Whether the permission evidence is complete (read-only).
   */
  permission_complete: boolean;
}
/**
 * The body of PUT /campaigns/{id}/accounts: the owner's own social
 * accounts that the campaign is run on (replaces the accounts before; an
 * account of a platform the campaign does not allow is refused).
 */
export interface CampaignAccounts {
  /**
   * @maxItems 50
   */
  account_ids: number[];
}
/**
 * The body of POST /campaigns/{id}/bulk-schedule: post every clip of
 * the campaign's projects to each of the campaign's own accounts (see
 * CampaignAccounts), each in the account's next free slot of rules, saying
 * text on every platform (a field left None takes the clip's own).
 * queue publishes them (human only), else they stay drafts with their
 * time.
 */
export interface CampaignBulkSchedule {
  /**
   * @minItems 1
   * @maxItems 200
   */
  clip_ids: [number, ...number[]];
  rules: ScheduleRules;
  text: PostText;
  queue: boolean;
}
/**
 * The rule checker's results for a clip (published on platform, or on
 * any of the campaign's platforms when None); campaign_id is None for a
 * project without a campaign, which only has the source_rights rule.
 */
export interface CampaignCheck {
  clip_id: number;
  campaign_id: number | null;
  platform:
    ("youtube" | "tiktok" | "instagram" | "facebook" | "x" | "linkedin") | null;
  results: RuleResult[];
  /**
   * Whether every rule passes: publishing is blocked otherwise
   * (read-only).
   */
  passed: boolean;
}
/**
 * Whether a clip passes one campaign rule; detail says what was found
 * or what the owner must fix.
 */
export interface RuleResult {
  rule:
    | "campaign_status"
    | "permission"
    | "source_rights"
    | "min_duration"
    | "max_duration"
    | "hashtags"
    | "credit_line"
    | "mentions"
    | "platform";
  passed: boolean;
  detail: string;
}
/**
 * What the owner enters for a clipping campaign (SPEC-v2 3.18): all of
 * it comes from forms and pasted text, nothing is fetched from a campaign
 * board. required_hashtags are stored without "#". rate_per_1k_usd is
 * None for an unpaid or unknown rate; monetization_allowed_elsewhere is
 * None while unknown; end_date (None: open-ended) is the last day that the
 * autopilot safety stop lets the campaign run (SPEC-v2 3.19). The
 * permission source URL is the page that shows the owner may clip the
 * creator; the screenshot is uploaded on its own.
 */
export interface CampaignCreate {
  name: string;
  creator_name: string;
  /**
   * @maxItems 50
   */
  source_channel_urls: string[];
  platform_board: "whop" | "direct" | "other";
  campaign_url: string | null;
  permission_source_url: string | null;
  badge: "open" | "register_first" | "apply_first" | "paid";
  rate_per_1k_usd: number | null;
  budget_note: string;
  allowed_platforms: ("youtube" | "tiktok" | "instagram")[];
  /**
   * @maxItems 30
   */
  required_hashtags: string[];
  required_credit_line: string;
  /**
   * @maxItems 30
   */
  required_tags_mentions: string[];
  min_duration_s: number | null;
  max_duration_s: number | null;
  banned_content_notes: string;
  monetization_allowed_elsewhere: boolean | null;
  submission_instructions: string;
  status: "active" | "paused" | "ended";
  notes: string;
  end_date: string | null;
  caption_template: string | null;
  allow_heavy_edits: "true" | "false" | "unknown";
}
/**
 * The body of PATCH /campaigns/{id}: only the fields that are sent
 * change (null clears a nullable field); at least one must be sent.
 */
export interface CampaignPatch {
  name: string;
  creator_name: string;
  /**
   * @maxItems 50
   */
  source_channel_urls: string[];
  platform_board: "whop" | "direct" | "other";
  campaign_url: string | null;
  permission_source_url: string | null;
  badge: "open" | "register_first" | "apply_first" | "paid";
  rate_per_1k_usd: number | null;
  budget_note: string;
  allowed_platforms: ("youtube" | "tiktok" | "instagram")[];
  /**
   * @maxItems 30
   */
  required_hashtags: string[];
  required_credit_line: string;
  /**
   * @maxItems 30
   */
  required_tags_mentions: string[];
  min_duration_s: number | null;
  max_duration_s: number | null;
  banned_content_notes: string;
  monetization_allowed_elsewhere: boolean | null;
  submission_instructions: string;
  status: "active" | "paused" | "ended";
  notes: string;
  end_date: string | null;
  caption_template: string | null;
  allow_heavy_edits: "true" | "false" | "unknown";
}
/**
 * Clip candidates as {"clips": [...]}: the reply the curate prompt asks
 * the LLM for (SPEC 6.5), and the content of candidates.json.
 */
export interface CandidateList {
  clips: ClipCandidate[];
}
/**
 * A clip proposed by the LLM; times are seconds from the video start.
 */
export interface ClipCandidate {
  start: number;
  end: number;
  title: string;
  hook_text: string;
  description: string;
  /**
   * @minItems 3
   * @maxItems 8
   */
  hashtags: [string, string, string, ...string[]];
  emphasis_words: string[];
  reason: string;
  hook: number;
  flow: number;
  value: number;
  trend: number;
}
/**
 * How a clip censors swear words (SPEC-v2 3.4, pipeline/censor): with
 * auto, the words of the default and custom censor lists; always, the
 * words a CaptionMark censors. A censored word's caption is masked
 * ("f***") and its sound beeped or muted, as mode says.
 */
export interface CaptionCensor {
  auto: boolean;
  mode: "beep" | "mute";
}
/**
 * One cue of translated captions: text shown from start to end (source
 * seconds), the time of the words it translates, said by speaker (the
 * transcript's label, "" if unknown).
 */
export interface CaptionCue {
  start: number;
  end: number;
  text: string;
  speaker: string;
}
/**
 * What the AI or the editor says of one caption word, the one that
 * starts at start (source seconds, to the millisecond): emphasis forces the
 * word to be an emphasis word or not (None: the clip's emphasis_words
 * decide), emoji is shown after it ("": none, None: the template's emoji
 * map decides) and color is the word's color while it is not the spoken
 * word, over the emphasis and speaker colors (None: they decide). A "user"
 * mark beats an "ai" mark of the same word.
 */
export interface CaptionMark {
  start: number;
  emphasis: boolean | null;
  emoji: string | "" | null;
  censor: boolean | null;
  color: string | null;
  source: "ai" | "user";
}
/**
 * What the editor changes of a clip's caption template: each field that
 * is set replaces the template's (size in pixels of the output frame); an
 * unset field keeps the template's. font must name a bundled font
 * (captions_templates.style_problems checks it when a clip is saved).
 *
 * speaker_colors (diarized speaker -> color of that speaker's words),
 * word_marks (per-word emphasis, emoji and censor), translation (the
 * captions in another language, shown instead of the transcript's words)
 * and censor (None: only the words that marks censor, beeped) belong to
 * the clip, not to a template: CaptionTemplate has no such fields.
 */
export interface CaptionStyle {
  size: number | null;
  primary_color: string | null;
  highlight_color: string | null;
  emphasis_color: string | null;
  position: ("top" | "middle" | "lower_third" | "bottom") | null;
  uppercase: boolean | null;
  emoji: boolean | null;
  font: string | null;
  outline: number | null;
  outline_color: string | null;
  shadow: number | null;
  box: boolean | null;
  max_lines: number | null;
  max_words_per_line: number | null;
  animation:
    | (
        | "none"
        | "pop"
        | "bounce"
        | "fade"
        | "reveal"
        | "shake"
        | "underline"
        | "pill"
        | "hollow"
      )
    | null;
  speaker_colors: {
    [k: string]: string;
  } | null;
  word_marks: CaptionMark[] | null;
  translation: CaptionTranslation | null;
  censor: CaptionCensor | null;
}
/**
 * A clip's captions in another language (pipeline/caption_translate):
 * the language's Whisper code and the translated cues, in time order.
 */
export interface CaptionTranslation {
  language: string;
  cues: CaptionCue[];
}
/**
 * How a caption template draws captions: the SPEC 6.9 template fields
 * and the SPEC-v2 3.4 ones (outline_color, max_lines, animation).
 *
 * font names a bundled font as libass selects it (clipforge.fonts). size is
 * the font size in pixels of the output frame (libass makes the font's OS/2
 * winAscent + winDescent that tall); outline (the stroke) and shadow are
 * pixels too. Words show in primary_color, the word being spoken in
 * highlight_color and the clip's emphasis words in emphasis_color at 110%
 * size; the stroke is outline_color. box puts an opaque box of
 * outline_color behind the text (the outline is then its padding). A line
 * holds at most max_words_per_line words and max_lines lines show at once;
 * animation says how words move (pipeline/caption_effects). emoji adds the
 * emoji of emoji_map.yaml after their keywords.
 */
export interface CaptionTemplate {
  font: string;
  size: number;
  primary_color: string;
  highlight_color: string;
  emphasis_color: string;
  outline: number;
  shadow: number;
  box: boolean;
  uppercase: boolean;
  position: "top" | "middle" | "lower_third" | "bottom";
  max_words_per_line: number;
  emoji: boolean;
  outline_color: string;
  max_lines: number;
  animation:
    | "none"
    | "pop"
    | "bounce"
    | "fade"
    | "reveal"
    | "shake"
    | "underline"
    | "pill"
    | "hollow";
}
/**
 * A caption template and where its preview image is.
 */
export interface CaptionTemplateInfo {
  name: string;
  template: CaptionTemplate;
  preview_url: string;
}
/**
 * POST /clips/{id}/caption-translation: the language (a Whisper code)
 * to translate the clip's captions into.
 */
export interface CaptionTranslationRequest {
  language: string;
}
/**
 * The custom censor list (SPEC-v2 3.4), censored with the default list
 * of the captions' language: whole words, any case; an entry ending in *
 * censors every word that starts with it.
 */
export interface CensorWords {
  /**
   * @maxItems 500
   */
  words: string[];
}
/**
 * A topic of a project's video: sentences from start to end seconds.
 *
 * id counts from 1. The chapters of a project follow each other without gap
 * or overlap and each one starts at the start of a sentence.
 */
export interface Chapter {
  id: number;
  start: number;
  end: number;
  title: string;
  summary: string;
}
/**
 * A topic chapter as the LLM proposes it (pipeline/chapters): its span in
 * seconds from the start of the video, a title and a one-line summary.
 */
export interface ChapterDraft {
  start: number;
  end: number;
  title: string;
  summary: string;
}
/**
 * The chapters of a project as {"chapters": [...]}: chapters.json.
 */
export interface ChapterList {
  chapters: Chapter[];
}
/**
 * The reply the chapters prompt asks the LLM for: {"chapters": [...]}.
 */
export interface ChapterReply {
  chapters: ChapterDraft[];
}
/**
 * The body of POST /clips/{id}/cleanup/apply: the items of a preview,
 * and the indexes of those the user unchecked, which stay.
 */
export interface CleanupApply {
  /**
   * @maxItems 2000
   */
  items: CleanupSuggestion[];
  unchecked?: number[];
}
/**
 * A cut that speech cleanup (polish, SPEC 6.10; pipeline/cleanup,
 * SPEC-v2 3.5) suggests for a clip, in seconds of the source: filler
 * words (text, with any pause around them), a pause (text "") or a bad
 * take (text: its words).
 */
export interface CleanupSuggestion {
  start: number;
  end: number;
  kind: "filler" | "pause" | "bad_take";
  text: string;
}
/**
 * The body of POST /clips/{id}/cleanup/preview: what speech cleanup
 * looks for. fillers: the filler words of the list of language (None: the
 * transcript's; a language without a list uses English) plus
 * extra_fillers; pauses: gaps longer than pause_threshold_s seconds;
 * bad_takes: repeated or abandoned sentences, found by the LLM.
 */
export interface CleanupOptions {
  fillers?: boolean;
  pauses?: boolean;
  pause_threshold_s?: number;
  bad_takes?: boolean;
  language?: string | null;
  /**
   * @maxItems 50
   */
  extra_fillers?: string[];
}
/**
 * What speech cleanup would remove from a clip, for review: items in
 * source order (none that the clip already cuts), and filler_language,
 * the code of the filler list it used.
 */
export interface CleanupPreview {
  filler_language: string;
  items: CleanupSuggestion[];
}
/**
 * A clip of a project: the segments of the source that it plays, in
 * order, and its timeline tracks; cut_ranges are removed [start, end]
 * sub-ranges. start and end (read-only) are the source span that the
 * segments cover: what v1 stored and the editor still edits.
 */
export interface Clip {
  id: number;
  project_id: number;
  /**
   * @minItems 1
   */
  segments: [[number, number], ...[number, number][]];
  tracks: Timeline;
  title: string;
  hook_text: string;
  description: string;
  hashtags: string[];
  emphasis_words: string[];
  reason: string;
  scores: Scores;
  layout:
    | "fill"
    | "fit"
    | "split"
    | "grid"
    | "pip"
    | "screenshare"
    | "gameplay"
    | "square_blur";
  caption_template: string;
  caption_overrides: Word[];
  cut_ranges: [number, number][];
  status: "candidate" | "rendering" | "rendered" | "failed";
  output_path: string | null;
  caption_style: CaptionStyle;
  crop_offset: number;
  framing: Framing;
  auto_cut: boolean;
  auto_zoom: boolean;
  zoom_keyframes: ZoomKeyframe[];
  scene_reframes: SceneReframe[];
  auto_color: boolean;
  show_captions: boolean;
  result_set: number;
  transitions: ClipTransitions;
  hook: ClipHook | null;
  enhance: number;
  parent_clip_id: number | null;
  variant: "original" | "pro_edit";
  /**
   * Where the earliest segment starts, in source seconds (read-only).
   */
  start: number;
  /**
   * Where the latest segment ends, in source seconds (read-only).
   */
  end: number;
}
/**
 * The tracks of a clip, each a list of items (SPEC-v2 4); the video
 * track holds a "source" item for each of the clip's segments.
 */
export interface Timeline {
  video: TrackItem[];
  broll: TrackItem[];
  overlays: TrackItem[];
  text: TrackItem[];
  music: TrackItem[];
  sfx: TrackItem[];
  voiceover: TrackItem[];
}
/**
 * An item on a track of a clip's timeline (SPEC-v2 4).
 *
 * A "source" item plays the [start, end] seconds of the source video
 * (one of the clip's segments) and has no asset_id. The items of the
 * other tracks show from start to end seconds of the rendered clip (after
 * its cuts); "video", "image" and "audio" items play asset asset_id, a
 * "text" item has none. props holds the settings of the item's track
 * (BrollProps, OverlayProps, TextProps, AudioProps or, on the music track,
 * MusicProps and on the voiceover track VoiceoverProps; clipforge.timeline).
 */
export interface TrackItem {
  id: string;
  kind: "source" | "video" | "image" | "text" | "audio";
  asset_id: number | null;
  start: number;
  end: number;
  props: {
    [k: string]: unknown;
  };
}
/**
 * Virality score breakdown of a clip.
 */
export interface Scores {
  overall: number;
  hook: number;
  flow: number;
  value: number;
  trend: number;
  laugh: number;
  energy: number;
}
/**
 * A transcribed word with its timing in seconds.
 */
export interface Word {
  text: string;
  start: number;
  end: number;
  speaker: string;
  prob: number;
  approximate: boolean;
}
/**
 * How the editor frames a clip on top of its crop plan
 * (pipeline/framing).
 *
 * aspect is the clip's (None: the project's); background is what the fit
 * layout shows around the video. The crop tool sizes the fill window to
 * scale times the planned window (1: the whole frame height) and puts it
 * at points, by time: with tracker on, the window follows the subject,
 * moved so it is at each point at that point's time; with tracker off, it
 * stays where the points put it (between two points it moves from one to
 * the other). facecam is the box the user drew around the facecam for the
 * screenshare and gameplay layouts (None: the one reframe found).
 */
export interface Framing {
  aspect: string | null;
  background: "blur" | "black";
  scale: number;
  points: CropPoint[];
  tracker: boolean;
  facecam: FrameBox | null;
}
/**
 * Where the editor's crop tool put a clip's fill window at t seconds
 * into the source: the window's center, in fractions of the source
 * frame's width (x) and height (y).
 */
export interface CropPoint {
  t: number;
  x: number;
  y: number;
}
/**
 * A box on the source frame: its top-left corner and size, in
 * fractions of the frame's width (x, width) and height (y, height).
 */
export interface FrameBox {
  x: number;
  y: number;
  width: number;
  height: number;
}
/**
 * The zoom of a clip's frames at t seconds into the source: scale 1 shows
 * the framed clip as it is, 1.15 magnifies it 15% (pipeline/auto_zoom).
 */
export interface ZoomKeyframe {
  t: number;
  scale: number;
}
/**
 * How a clip frames one scene, start to end seconds of the source
 * (pipeline/scenes). layout is the scene's; with fill, mode says where
 * its fill window is: auto follows the clip's crop plan (with the clip's
 * crop offset and crop tool), track and fixed put the window's center at
 * crop_keyframes (linear between them, held before the first and after
 * the last; fixed without keyframes holds the auto window of the scene's
 * start). The window is scale times the planned window. track_seed is the
 * box that the track mode's keyframes were tracked from.
 */
export interface SceneReframe {
  start: number;
  end: number;
  mode: "auto" | "track" | "fixed";
  layout:
    | "fill"
    | "fit"
    | "split"
    | "grid"
    | "pip"
    | "screenshare"
    | "gameplay"
    | "square_blur";
  crop_keyframes: CropPoint[];
  scale: number;
  track_seed: TrackSeed | null;
}
/**
 * The box the editor drew (or clicked) around a subject to track, at t
 * seconds into the source: its top-left corner and size, in fractions of
 * the source frame's width (x, width) and height (y, height).
 */
export interface TrackSeed {
  t: number;
  x: number;
  y: number;
  width: number;
  height: number;
}
/**
 * The transitions of a clip's render (SPEC-v2 3.5): auto at every jump
 * cut (a cut inside a section: its cut ranges, the auto cut's too), and
 * sections[i] at the cut from the i-th to the next section in play order
 * (manual; None, or no entry: a hard cut). Entries past the clip's last
 * section boundary are kept but not used.
 */
export interface ClipTransitions {
  auto: Transition | null;
  /**
   * @maxItems 100
   */
  sections: (Transition | null)[];
}
/**
 * A transition at a cut of a clip's render: kind over duration seconds,
 * centred on the cut (pipeline/transitions).
 */
export interface Transition {
  kind: "crossfade" | "zoom_punch" | "whip" | "slide";
  duration: number;
}
/**
 * The viral hook of a clip (SPEC-v2 3.5, pipeline/hooks): over the
 * first duration seconds of its render, the hook template template
 * (clipforge.hooks_templates) draws text with its animations, punches
 * in on the frames and plays its whoosh. While a clip has one, its v1
 * hook_text is not drawn.
 */
export interface ClipHook {
  template: string;
  text: string;
  duration: number;
}
/**
 * Body of POST /search/clips: make a clip of the project's video from
 * the moment at seconds (a search hit's start), as long as length seconds
 * at most, from the start of the sentence that holds the moment to the end
 * of a sentence.
 */
export interface ClipFromMoment {
  project_id: number;
  at: number;
  length: number;
}
/**
 * The undo/redo history of a clip: its versions, oldest first, and the
 * number of the one the clip shows (current; 0 before its first edit).
 * Undo goes to the version before current, redo to the one after.
 */
export interface ClipHistory {
  current: number;
  can_undo: boolean;
  can_redo: boolean;
  versions: ClipVersionInfo[];
}
/**
 * A version of a clip in its history, without its state. number grows
 * with each version and is never reused; fields are the ClipState fields
 * that differ from the version before it (empty for the original);
 * restored_from is the version a restore copied.
 */
export interface ClipVersionInfo {
  number: number;
  kind: "original" | "edit" | "restore";
  created_at: string;
  fields: string[];
  restored_from: number | null;
}
/**
 * The body of PATCH /clips/{id}: the fields to change (unset or null
 * fields are kept). start and end move the clip's span: where its earliest
 * segment in the source starts and its latest one ends. The API also
 * checks the result: start < end within the source, cut_ranges inside the
 * clip, a known caption template, scenes that cover the clip in order (or
 * none).
 */
export interface ClipPatch {
  start?: number | null;
  end?: number | null;
  title?: string | null;
  hook_text?: string | null;
  description?: string | null;
  hashtags?: string[] | null;
  layout?:
    | (
        | "fill"
        | "fit"
        | "split"
        | "grid"
        | "pip"
        | "screenshare"
        | "gameplay"
        | "square_blur"
      )
    | null;
  caption_template?: string | null;
  caption_overrides?: Word[] | null;
  caption_style?: CaptionStyle | null;
  crop_offset?: number | null;
  framing?: Framing | null;
  cut_ranges?: [number, number][] | null;
  auto_cut?: boolean | null;
  auto_zoom?: boolean | null;
  zoom_keyframes?: ZoomKeyframe[] | null;
  auto_color?: boolean | null;
  show_captions?: boolean | null;
  scene_reframes?: SceneReframe[] | null;
  transitions?: ClipTransitions | null;
}
/**
 * A clip's scenes (GET /clips/{id}/scenes): the scene cuts of its
 * source, in seconds, and its scenes as stored, or split at the cuts
 * inside it if it has none stored (default_scenes).
 */
export interface ClipScenes {
  cuts: number[];
  scenes: SceneReframe[];
}
/**
 * The body of POST /clips/{id}/split: split the clip in two at at
 * seconds of the source (inside one of its sections, or on the edge between
 * two); the clip keeps what plays before, a new clip gets what plays
 * after.
 */
export interface ClipSplit {
  at: number;
}
/**
 * What a version of a clip keeps (SPEC-v2 3.5 versions): every field
 * of the clip that an edit changes. Not its status, render, scores or
 * result set.
 */
export interface ClipState {
  /**
   * @minItems 1
   */
  segments: [[number, number], ...[number, number][]];
  tracks: Timeline;
  title: string;
  hook_text: string;
  description: string;
  hashtags: string[];
  emphasis_words: string[];
  layout:
    | "fill"
    | "fit"
    | "split"
    | "grid"
    | "pip"
    | "screenshare"
    | "gameplay"
    | "square_blur";
  caption_template: string;
  caption_overrides: Word[];
  cut_ranges: [number, number][];
  caption_style: CaptionStyle;
  crop_offset: number;
  framing: Framing;
  auto_cut: boolean;
  auto_zoom: boolean;
  zoom_keyframes: ZoomKeyframe[];
  scene_reframes: SceneReframe[];
  auto_color: boolean;
  show_captions: boolean;
  transitions: ClipTransitions;
  hook: ClipHook | null;
  enhance: number;
}
/**
 * A clip's title, description and hashtags as the LLM rewrites them
 * (POST /clips/{id}/regenerate-text), with ClipCandidate's limits.
 */
export interface ClipText {
  title: string;
  description: string;
  /**
   * @minItems 3
   * @maxItems 8
   */
  hashtags: [string, string, string, ...string[]];
}
/**
 * A version of a clip with the clip's state at that version.
 */
export interface ClipVersion {
  number: number;
  kind: "original" | "edit" | "restore";
  created_at: string;
  fields: string[];
  restored_from: number | null;
  state: ClipState;
}
/**
 * A named, ordered set of clips from any projects (SPEC-v2 3.11, 4:
 * Collection); clip_count is how many it holds.
 */
export interface Collection {
  id: number;
  name: string;
  description: string;
  created_at: string;
  updated_at: string;
  clip_count: number;
}
/**
 * Body of POST /collections/{id}/items: the clips to add, at the end in
 * this order (those already in the collection stay where they are).
 */
export interface CollectionAddClips {
  /**
   * @minItems 1
   * @maxItems 500
   */
  clip_ids: [number, ...number[]];
}
/**
 * What a collection shows of one of its clips: where it comes from, its
 * title and status, its overall score and its source span.
 */
export interface CollectionClip {
  id: number;
  project_id: number;
  title: string;
  status: "candidate" | "rendering" | "rendered" | "failed";
  overall: number;
  start: number;
  end: number;
}
/**
 * Body of POST /collections.
 */
export interface CollectionCreate {
  name: string;
  description: string;
}
/**
 * A collection with its items, in their order.
 */
export interface CollectionDetail {
  id: number;
  name: string;
  description: string;
  created_at: string;
  updated_at: string;
  clip_count: number;
  items: CollectionItem[];
}
/**
 * A clip in a collection (SPEC-v2 4: CollectionItem); position 0 is the
 * first of the collection.
 */
export interface CollectionItem {
  id: number;
  collection_id: number;
  clip_id: number;
  position: number;
  added_at: string;
  clip: CollectionClip;
}
/**
 * The manifest.json of a collection's zip: the clips in it, in the
 * collection's order, and those left out.
 */
export interface CollectionManifest {
  collection_id: number;
  name: string;
  description: string;
  exported_at: string;
  clips: CollectionManifestClip[];
  skipped: CollectionManifestSkipped[];
}
/**
 * One clip of a collection's zip, as manifest.json lists it: file is its
 * video's name in the zip.
 */
export interface CollectionManifestClip {
  clip_id: number;
  project_id: number;
  title: string;
  hook_text: string;
  description: string;
  hashtags: string[];
  overall: number;
  start: number;
  end: number;
  file: string;
}
/**
 * A clip of the collection that the zip leaves out, and why.
 */
export interface CollectionManifestSkipped {
  clip_id: number;
  reason: string;
}
/**
 * Body of PATCH /collections/{id}: the fields to change.
 */
export interface CollectionUpdate {
  name: string | null;
  description: string | null;
}
/**
 * One critic round (from 1): the scores of plan version plan_version
 * and the revision it led to (changes: "what changed"; ignored: the
 * critic's changes left out and why; notes: what else stopped or bent
 * the revision). A round that passed or stopped the loop changes
 * nothing.
 */
export interface CriticRound {
  round: number;
  scores: CriticScore[];
  plan_version: number | null;
  changes: PlanChange[];
  ignored: IgnoredChange[];
  notes: string[];
}
/**
 * What the critic scored one checklist point (SPEC-v3 3.7), 0 to 10,
 * and why.
 */
export interface CriticScore {
  check: string;
  score: number;
  reason: string;
}
/**
 * One difference between a plan and its critic revision ("what
 * changed"): item item_id before and after (before None: added; after
 * None: removed) and why it changed (the critic's reason, or what
 * post-processing did).
 */
export interface PlanChange {
  op: "add" | "remove" | "modify";
  item_id: number;
  before: EdlItem | null;
  after: EdlItem | null;
  reason: string;
}
/**
 * One edit decision of a Pro Edit plan (SPEC-v3 3.1): kind from t_start
 * to t_end in seconds of the clip, with its params and the reason that the
 * UI shows. id numbers the item within its plan, from 1.
 */
export interface EdlItem {
  id: number;
  t_start: number;
  t_end: number;
  kind:
    | "zoom_punch"
    | "zoom_push"
    | "zoom_out_reveal"
    | "pan"
    | "shake"
    | "flash"
    | "glitch"
    | "rgb_split"
    | "freeze_frame"
    | "speed_ramp"
    | "slowmo"
    | "transition"
    | "grade_change"
    | "vignette"
    | "grain"
    | "overlay"
    | "text_pop"
    | "emoji_pop"
    | "caption_style"
    | "sfx"
    | "music_bed"
    | "silence_before_drop"
    | "audio_fx";
  params: {
    [k: string]: unknown;
  };
  reason: string;
  source: "auto" | "manual";
}
/**
 * A change the critic asked for that was not applied: what it asked
 * (op on item_id, or the kind it would add), its reason and the problem
 * that made the code ignore it.
 */
export interface IgnoredChange {
  op: "add" | "remove" | "modify";
  item_id: number | null;
  kind:
    | (
        | "zoom_punch"
        | "zoom_push"
        | "zoom_out_reveal"
        | "pan"
        | "shake"
        | "flash"
        | "glitch"
        | "rgb_split"
        | "freeze_frame"
        | "speed_ramp"
        | "slowmo"
        | "transition"
        | "grade_change"
        | "vignette"
        | "grain"
        | "overlay"
        | "text_pop"
        | "emoji_pop"
        | "caption_style"
        | "sfx"
        | "music_bed"
        | "silence_before_drop"
        | "audio_fx"
      )
    | null;
  reason: string;
  problem: string;
}
/**
 * The crop window's left edge x at t seconds into the source, and the
 * faces seen then, largest first; y, if set, is the window's top then
 * (else the plan's y).
 */
export interface CropKeyframe {
  t: number;
  x: number;
  faces: FaceBox[];
  y: number | null;
}
/**
 * A face (or, where no face was seen, a person; in a shot without
 * either, the moving object of pipeline/object_tracking) that reframe
 * detected; x, y, width and height are pixels of the source frame, (x, y) the
 * top-left corner. mouth is how open the face's mouth is (lip gap over
 * face height; None if not measured); track identifies the same face
 * across the samples of a shot (pipeline/identity; None if not tracked);
 * subject marks the face the fill window follows (pipeline/speaker).
 */
export interface FaceBox {
  x: number;
  y: number;
  width: number;
  height: number;
  score: number;
  kind: "face" | "person" | "object";
  mouth: number | null;
  track: number | null;
  subject: boolean;
}
/**
 * The body of PUT /clips/{id}/crop-keyframes (pipeline/keyframes): the
 * crop box dragged to center (x, y), in fractions of the source frame, at
 * t seconds of the source, and resized to scale times the planned window
 * (None: the scene's scale is kept).
 */
export interface CropKeyframeSet {
  t: number;
  x: number;
  y: number;
  scale: number | null;
}
/**
 * How to frame a clip for its aspect: crop_<clip_id>.json (SPEC 6.8).
 *
 * The fill window of width x height source pixels at top y follows the
 * subject with one keyframe per frame sampled from start to end (5 a
 * second). split holds the top and bottom windows of the split layout,
 * which follow the left and the right speaker; grid the three windows of
 * the grid layout, which follow the left, middle and right speaker (empty
 * in a plan made before the grid layout: pipeline/layout_windows adds
 * them); inset the window of the pip layout's inset, which follows the
 * largest face that is not the subject (None: the inset shows the whole
 * frame). facecam is the box around the subject's face that the
 * screenshare and gameplay layouts show (None: no face was found, or the
 * plan was made before these layouts). layout is the one reframe chose
 * for the clip. background is the fit layout's (reframe writes the
 * default; pipeline/framing sets the clip's before a render).
 */
export interface CropPlan {
  clip_id: number;
  start: number;
  end: number;
  aspect: string;
  width: number;
  height: number;
  y: number;
  keyframes: CropKeyframe[];
  layout:
    | "fill"
    | "fit"
    | "split"
    | "grid"
    | "pip"
    | "screenshare"
    | "gameplay"
    | "square_blur";
  /**
   * @minItems 2
   * @maxItems 2
   */
  split: [CropWindow, CropWindow];
  grid: CropWindow[];
  inset: CropWindow | null;
  facecam: FrameBox | null;
  background: "blur" | "black";
  preset: ("podcast-2" | "standup" | "gaming" | "vlog") | null;
  camera_motion: ("calm" | "normal" | "fast") | null;
}
/**
 * A window of width x height source pixels at top y whose left edge is
 * xs[k] at keyframe k of its crop plan.
 */
export interface CropWindow {
  width: number;
  height: number;
  y: number;
  xs: number[];
}
/**
 * The fill window that reframe planned for a clip in aspect, as the
 * editor's crop tool draws it (GET /clips/{id}/crop): a width x height
 * window at top y of the frame_width x frame_height source, whose left
 * edge is xs[k] at times[k] source seconds. facecam is the facecam box
 * that reframe found for the screenshare and gameplay layouts (None: the
 * clip shows no face).
 */
export interface CropTrack {
  aspect: string;
  frame_width: number;
  frame_height: number;
  width: number;
  height: number;
  y: number;
  times: number[];
  xs: number[];
  facecam: FrameBox | null;
}
/**
 * A clip that the autopilot made for the owner to decide on (SPEC-v2
 * 3.19). A clip that passes the campaign's rules waits as pending in the
 * Approval Inbox; one that fails is needs_fix, with the failed rules in
 * rule_results. The owner moves it to approved or rejected (decided_at,
 * reject_reason), or it expires after the campaign's draft_ttl_days
 * (created_at is when it was made). notes are the review notes of the
 * owner and of agents, oldest first. Approving and rejecting are the
 * owner's alone (human-only, SPEC-v2 3.19).
 */
export interface Draft {
  id: number;
  clip_id: number;
  campaign_id: number;
  status: "pending" | "needs_fix" | "approved" | "rejected" | "expired";
  rule_results: RuleResult[];
  reject_reason:
    | (
        | "boring"
        | "out_of_context"
        | "bad_crop"
        | "bad_captions"
        | "too_long"
        | "other"
      )
    | null;
  decided_at: string | null;
  created_at: string;
  notes: DraftNote[];
}
/**
 * A review note of a draft: text, who wrote it (by) and when (at).
 */
export interface DraftNote {
  text: string;
  by: "owner" | "agent";
  at: string;
}
/**
 * An approved draft and the queued posts of its clip.
 */
export interface DraftApproval {
  draft: Draft;
  posts: Post[];
}
/**
 * A clip posted (or to be posted) to one social account (SPEC-v2 3.10,
 * 4). payload holds the platform's post fields (title, caption, privacy,
 * ...). status moves draft -> queued -> uploading -> published | failed |
 * canceled; a queued post missed while the app was off may be skipped
 * (clipforge.posts has the legal moves); attempts counts the
 * uploads started since it was last queued, attempted_at is when the
 * latest one started and next_attempt_at holds a queued post back until
 * then (retry backoff, rate limit, quota). account_id is None once its
 * account was disconnected (the post's history stays).
 */
export interface Post {
  id: number;
  clip_id: number;
  account_id: number | null;
  platform: "youtube" | "tiktok" | "instagram" | "facebook" | "x" | "linkedin";
  payload: {
    [k: string]: unknown;
  };
  thumbnail_asset_id: number | null;
  scheduled_at: string | null;
  status:
    | "draft"
    | "queued"
    | "uploading"
    | "published"
    | "failed"
    | "canceled"
    | "skipped";
  external_post_id: string | null;
  url: string | null;
  error: string | null;
  attempts: number;
  attempted_at: string | null;
  next_attempt_at: string | null;
}
/**
 * The body of POST /drafts/{id}/approve and of
 * POST /campaigns/{id}/drafts/approve (the owner only): the posting rules
 * (None: the autopilot's slots; one of them is needed) and what the posts
 * say (a field left None takes the clip's own). Each post goes into its
 * account's next free slot, at most max_posts_per_day a day.
 */
export interface DraftApprove {
  rules: ScheduleRules | null;
  text: PostText;
}
/**
 * The body of POST /drafts: make a draft of clip clip_id (a clip of a
 * campaign's project) for the owner's Approval Inbox. It is pending if the
 * clip passes the campaign's rules, else needs_fix.
 */
export interface DraftCreate {
  clip_id: number;
}
/**
 * The body of POST /drafts/{id}/notes: a review note to add.
 */
export interface DraftNoteCreate {
  text: string;
}
/**
 * The body of POST /drafts/{id}/reject (the owner only): why, if the
 * owner says (the reason chips).
 */
export interface DraftReject {
  reason:
    | (
        | "boring"
        | "out_of_context"
        | "bad_crop"
        | "bad_captions"
        | "too_long"
        | "other"
      )
    | null;
}
/**
 * The Google sign-in page that connects an account.
 */
export interface DriveConnect {
  authorize_url: string;
}
/**
 * A Drive video: its id, file name, MIME type, size in bytes and
 * duration in seconds (None when Drive does not say).
 */
export interface DriveFile {
  id: string;
  name: string;
  mime_type: string;
  size: number | null;
  duration: number | null;
}
/**
 * The body of POST /sources/gdrive/file: a Drive file link or id.
 */
export interface DriveFileRequest {
  file: string;
}
/**
 * The body of POST /sources/gdrive/import: the Drive file link or id,
 * how to process it and its source rights, as in ProjectCreate.
 */
export interface DriveImport {
  file: string;
  settings?: ProcessingSettings;
  source_rights?:
    ("own" | "permission" | "cc_by" | "public_domain" | "other") | null;
  credit_line?: string;
}
/**
 * Whether the Google OAuth app is configured and an account connected.
 */
export interface DriveStatus {
  configured: boolean;
  connected: boolean;
}
/**
 * The Dropbox sign-in page that connects an account.
 */
export interface DropboxConnect {
  authorize_url: string;
}
/**
 * A Dropbox video behind a shared link: the link, file name and size in
 * bytes.
 */
export interface DropboxFile {
  url: string;
  name: string;
  size: number;
}
/**
 * The body of POST /sources/dropbox/file: a Dropbox shared file link.
 */
export interface DropboxFileRequest {
  file: string;
}
/**
 * The body of POST /sources/dropbox/import: the shared file link, how to
 * process it and its source rights, as in ProjectCreate.
 */
export interface DropboxImport {
  file: string;
  settings?: ProcessingSettings;
  source_rights?:
    ("own" | "permission" | "cc_by" | "public_domain" | "other") | null;
  credit_line?: string;
}
/**
 * Whether the Dropbox app is configured and an account connected.
 */
export interface DropboxStatus {
  configured: boolean;
  connected: boolean;
}
/**
 * One engine as `GET /api/engines` returns it: the capability flag
 * (`installed`) the UI reads, and the README section for its setup.
 */
export interface EngineStatus {
  name: string;
  label: string;
  installed: boolean;
  version: string | null;
  error: string | null;
  doc_anchor: string;
}
/**
 * Every error answer of the API (SPEC 7): a short code (not_found,
 * api_key_invalid, rate_limited, ...) and a sentence for the user. Some
 * errors add fields (e.g. the failed campaign rules).
 */
export interface ErrorBody {
  error: string;
  message: string;
  [k: string]: unknown;
}
/**
 * The payload of a Facebook Page reel (SPEC-v2 3.10, Facebook's Reels
 * publishing rules). description (hashtags included) defaults to the
 * clip's title + hashtags; title is shown with the reel when given;
 * ai_generated labels AI content; collaborator_page_ids are the ids of up
 * to 10 other Facebook Pages invited to publish the reel too (Facebook
 * allows 10 invitations per Page per 24 h). Reels publish to the Page
 * publicly. Keys of other platforms are ignored.
 */
export interface FacebookPostOptions {
  title: string | null;
  description: string | null;
  ai_generated: boolean;
  /**
   * @maxItems 10
   */
  collaborator_page_ids: string[];
}
/**
 * What the owner decided about a clip of a campaign (SPEC-v2 3.19):
 * approved, or rejected with a reason. It teaches the next curate prompt
 * and score of the campaign. clip_id is None once the clip was deleted
 * (what was learned stays).
 */
export interface FeedbackEvent {
  id: number;
  clip_id: number | null;
  campaign_id: number;
  action: "approved" | "rejected";
  reason:
    | (
        | "boring"
        | "out_of_context"
        | "bad_crop"
        | "bad_captions"
        | "too_long"
        | "other"
      )
    | null;
  at: string;
}
/**
 * A font of the asset library (SPEC-v2 3.4): names are what a caption
 * style or brand template calls it (family and full name); bundled fonts
 * come with ClipForge, the others were uploaded.
 */
export interface FontFile {
  asset: Asset;
  names: string[];
  bundled: boolean;
}
/**
 * What the vision model saw in the source frame at time (source
 * seconds), which was sampled for reason.
 */
export interface FrameCaption {
  time: number;
  reason: "scene_cut" | "interval";
  caption: string;
}
/**
 * The content of frame_captions.json: the Ollama vision model that
 * wrote the captions, and the captions by time.
 */
export interface FrameCaptionList {
  model: string;
  captions: FrameCaption[];
}
/**
 * The body of POST /clips/{id}/headline: the clip's headline text, or
 * null to have the LLM write one (pipeline/headline).
 */
export interface HeadlineApply {
  text: string | null;
}
/**
 * The body of POST /clips/{id}/hook: give the clip the hook template
 * template for duration seconds, its text taken from source: the opening
 * words of its captions, a line the LLM writes about its theme, or text
 * (which source "text" needs). duration None: the template's.
 */
export interface HookApply {
  template: string;
  source: "captions" | "theme" | "text";
  text: string | null;
  duration: number | null;
}
/**
 * The body of PATCH /clips/{id}/hook: the fields of the clip's hook to
 * change (unset or null: kept).
 */
export interface HookEdit {
  template: string | null;
  text: string | null;
  duration: number | null;
}
/**
 * The LLM's reply with one line of text for a clip: a hook line about
 * its theme or its headline.
 */
export interface HookLine {
  text: string;
}
/**
 * A hook template as GET /hook-templates lists it: name (what
 * ClipHook.template names), label and description to show, the seconds
 * a hook lasts by default, the most its punch-in magnifies the frames
 * (1: none) and whether it plays a whoosh.
 */
export interface HookTemplateInfo {
  name: string;
  label: string;
  description: string;
  duration: number;
  punch: number;
  sound: boolean;
}
/**
 * The payload of an Instagram Reels post (SPEC-v2 3.10, Instagram's
 * content publishing rules). caption defaults to the clip's title +
 * hashtags (at most 2200 characters, 30 hashtags and 20 @ tags);
 * share_to_feed also shows the reel in the feed; collaborators are up to
 * 3 Instagram usernames invited as collaborators; thumb_offset_ms picks
 * the cover frame (Instagram takes cover images only from public URLs);
 * audio_name names the reel's original audio; ai_generated labels AI
 * content; trial_strategy posts a trial reel shown to non-followers only
 * (graduated by hand, MANUAL, or when it performs well). Keys of other
 * platforms are ignored.
 */
export interface InstagramPostOptions {
  caption: string | null;
  share_to_feed: boolean;
  /**
   * @maxItems 3
   */
  collaborators: string[];
  thumb_offset_ms: number | null;
  audio_name: string | null;
  ai_generated: boolean;
  trial_strategy: ("MANUAL" | "SS_PERFORMANCE") | null;
}
/**
 * What `install_check` found: whether the engine is usable, its version
 * when it has one, and why it is not installed (None when it is).
 */
export interface InstallStatus {
  installed: boolean;
  version: string | null;
  error: string | null;
}
/**
 * A queued unit of work; progress is a fraction from 0 to 1. The worker
 * pool runs the queued job with the highest priority first (then the
 * oldest); attempts counts the times a worker started it.
 */
export interface Job {
  id: number;
  project_id: number;
  clip_id: number | null;
  kind: "process" | "render" | "reprompt" | "proedit";
  step: string;
  progress: number;
  status: "queued" | "running" | "done" | "failed";
  error: string | null;
  log_path: string;
  priority: number;
  attempts: number;
  overall_progress: number;
  eta_seconds: number | null;
}
/**
 * The month's total of one kind: units (seconds for compute), the cost in
 * USD of the paid records (None if no record has a cost), the monthly cap in
 * the same units (None if there is none) and whether the total reached it.
 */
export interface KindUsage {
  kind: string;
  units: number;
  cost_usd: number | null;
  cap: number | null;
  exceeded: boolean;
}
/**
 * The models that the provider offers (the provider's own order), or why
 * they could not be listed. A provider with no list (Claude Code) gives no
 * models and no error.
 */
export interface LlmModels {
  models: string[];
  error: string | null;
}
/**
 * The outcome of a connection test: ok, and a message that is the
 * start of the model's reply or the reason that it failed.
 */
export interface LlmTestResult {
  ok: boolean;
  provider: string;
  model: string;
  message: string;
}
/**
 * A file of the media library (SPEC-v2 3.5): an image, logo, video or
 * audio asset the owner uploaded. tags are the owner's; used_in_clips lists
 * the clips whose timeline plays the file, and a file that a clip uses
 * cannot be deleted.
 */
export interface MediaItem {
  asset: Asset;
  tags: string[];
  name: string;
  mime: string;
  size_bytes: number;
  duration: number | null;
  width: number | null;
  height: number | null;
  has_thumbnail: boolean;
  used_in_clips: number[];
}
/**
 * What the media library keeps of an uploaded file, next to it: the name
 * the client gave, the MIME type from its first bytes, its size, what
 * ffprobe read (duration for video and audio, size in pixels for video and
 * images) and the file name of its thumbnail, if it has one.
 */
export interface MediaMeta {
  name: string;
  mime: string;
  size_bytes: number;
  duration: number | null;
  width: number | null;
  height: number | null;
  thumbnail: string | null;
}
/**
 * The changes of a media library file: send what changes.
 */
export interface MediaUpdate {
  tags: string[] | null;
  license: string | null;
  attribution: string | null;
}
/**
 * A motion graphic that the LLM picks for a clip: kind, the text to
 * show and a short label under it ("" for none: a name's role, what a
 * number counts), and quote, the words of the clip it goes with, as they
 * are said (the graphic shows from the first of them).
 */
export interface MotionGraphicPick {
  kind: "name" | "number" | "date" | "phrase";
  text: string;
  label: string;
  quote: string;
}
/**
 * The body of POST /clips/{id}/motion-graphics: place at most
 * max_items motion graphics (fewer if the text track has no room).
 */
export interface MotionGraphicsApply {
  max_items: number;
}
/**
 * The LLM's reply with the motion graphics of a clip, in any order
 * (none if it says nothing worth one).
 */
export interface MotionGraphicsReply {
  /**
   * @maxItems 10
   */
  items: MotionGraphicPick[];
}
/**
 * How much the picture moves, per second: the content of motion.json.
 *
 * scores[i] is the motion energy of the second that starts at start + i
 * (source seconds): the median, over the frame pairs of that second, of
 * the mean absolute difference of two consecutive small grey frames, as a
 * fraction of full scale (0: a still picture).
 */
export interface MotionTrack {
  start: number;
  scores: number[];
}
/**
 * The props of a music item (SPEC-v2 3.5, pipeline/music): an
 * AudioProps whose file loops for as long as the item lasts, fading in
 * over fade_in seconds from its start and out over fade_out seconds to
 * its end, and, if duck, dipping under the clip's speech (a sidechain
 * compressor keyed by the clip's sound).
 */
export interface MusicProps {
  volume: number;
  offset: number;
  fade_in: number;
  fade_out: number;
  duck: boolean;
}
/**
 * A track of the music library (SPEC-v2 3.5): a bundled loop
 * (assets/music, with its title and mood tags) or a music file uploaded
 * to the media library (its file name and the owner's tags). duration is
 * the file's length in seconds (None if ffprobe cannot read it).
 */
export interface MusicTrack {
  asset: Asset;
  title: string;
  duration: number | null;
  bundled: boolean;
  tags: string[];
}
/**
 * A message for the owner (SPEC-v2 3.17): what happened (title, body),
 * where to see it (link, an app path such as /projects/3) and when;
 * read_at is None until the owner reads it.
 */
export interface Notification {
  id: number;
  kind:
    | "project_done"
    | "render_failed"
    | "post_published"
    | "post_failed"
    | "quota_warning"
    | "autopilot_stopped"
    | "digest"
    | "test";
  title: string;
  body: string;
  link: string | null;
  created_at: string;
  read_at: string | null;
}
/**
 * GET /notifications/channels: where a notification goes besides the
 * app. email is on only if SMTP_HOST is set; email_to is the recipient.
 */
export interface NotificationChannels {
  email: boolean;
  email_to: string | null;
  desktop: boolean;
}
/**
 * GET /notifications: the newest notifications, and how many unread ones
 * there are in all.
 */
export interface NotificationList {
  items: Notification[];
  unread_count: number;
}
/**
 * The props of an overlay item: the asset, width times the frame's
 * width wide, centered at (x, y) in fractions of the frame, at opacity; a
 * video asset plays from offset seconds, muted.
 */
export interface OverlayProps {
  x: number;
  y: number;
  width: number;
  opacity: number;
  offset: number;
}
/**
 * Whether ClipForge can publish to a platform (supported) and whether
 * the owner's developer app for it is set (configured); settings_keys name
 * the settings (env vars) that hold the app's keys.
 */
export interface PlatformStatus {
  platform: "youtube" | "tiktok" | "instagram" | "facebook" | "x" | "linkedin";
  supported: boolean;
  configured: boolean;
  settings_keys: string[];
}
/**
 * What a post says on one platform, as the Schedule post form holds
 * it: title (empty on platforms whose post has none; the headline then
 * starts the caption), caption (the description) and hashtags without
 * "#".
 */
export interface PostCopy {
  title: string;
  caption: string;
  hashtags: string[];
}
/**
 * The LLM's headline, description and hashtags of a post.
 */
export interface PostCopyReply {
  /**
   * @maxItems 50
   */
  hashtags: string[];
  title: string;
  description: string;
}
/**
 * The body of POST /clips/{id}/post-copy: write the post of the clip on
 * platform. Without options the whole copy is new. tone and format
 * rewrite the title and caption (current says what they are now);
 * hashtags (more, fewer, none) changes only the hashtags. account_id is
 * the account the post is for: its always_hashtags are added to the
 * always-included ones.
 */
export interface PostCopyRequest {
  platform: "youtube" | "tiktok" | "instagram" | "facebook";
  tone: ("casual" | "punchy" | "professional" | "funny") | null;
  format: ("short" | "list" | "story") | null;
  hashtags: ("more" | "fewer" | "none") | null;
  current: PostCopy | null;
  account_id: number | null;
}
/**
 * The body of POST /clips/{id}/posts: draft posts of the clip to each
 * target account, to publish at scheduled_at (None: not scheduled yet)
 * with the thumbnail asset, if any.
 */
export interface PostCreate {
  /**
   * @minItems 1
   * @maxItems 50
   */
  targets: [PostTarget, ...PostTarget[]];
  scheduled_at: string | null;
  thumbnail_asset_id: number | null;
}
/**
 * The body of PATCH /posts/{id}: a new text, time (reschedule; null:
 * unscheduled) or thumbnail of a draft or queued post. Fields left out
 * keep their value.
 */
export interface PostPatch {
  text: PostText | null;
  scheduled_at: string | null;
  thumbnail_asset_id: number | null;
}
/**
 * The body of POST /posts/{id}/queue: publish the post at scheduled_at
 * (left out: its own time; null: as soon as possible).
 */
export interface PostQueue {
  scheduled_at: string | null;
}
/**
 * The LLM's hashtags of a post.
 */
export interface PostTagsReply {
  /**
   * @maxItems 50
   */
  hashtags: string[];
}
/**
 * The LLM's headline and description of a post (limits are applied to
 * the platform afterwards, by cutting).
 */
export interface PostTextReply {
  title: string;
  description: string;
}
/**
 * What the Pro Edit dialog offers for one clip (SPEC-v3 3.8): the
 * presets, the music beds and style recipes to pick from, the campaign of
 * the clip's project (None: none) with whether its rules allow heavy
 * edits, and the highest intensity the slider reaches (the campaign
 * autopilot's Pro Edit cap once the owner saved it, else extreme).
 */
export interface ProEditChoices {
  presets: ProEditPresetInfo[];
  music: ProEditMusicOption[];
  recipes: StyleRecipe[];
  campaign_id: number | null;
  campaign_name: string | null;
  allow_heavy_edits: ("true" | "false" | "unknown") | null;
  max_intensity: "clean" | "standard" | "pro" | "extreme";
}
/**
 * A preset as the Pro Edit dialog shows it (SPEC-v3 3.4): its id,
 * display name, one-line description and the moods and BPM range of the
 * music it picks.
 */
export interface ProEditPresetInfo {
  id:
    | "clean_pro"
    | "dark_edit"
    | "phonk_edit"
    | "cinematic"
    | "skull_moment"
    | "glitch";
  name: string;
  description: string;
  music_moods: string[];
  bpm_min: number;
  bpm_max: number;
}
/**
 * A music bed the owner may pick for a Pro Edit: id is what
 * ProEditOptions.music takes (a bundled loop's name or a library asset
 * id), with its title, mood tags and whether it is a bundled loop.
 */
export interface ProEditMusicOption {
  id: string;
  title: string;
  tags: string[];
  bundled: boolean;
}
/**
 * A look and feel learned from reference links (SPEC-v3 4): features
 * are the aggregated numbers (medians and ranges) and description a short
 * text about them. It never holds media or media paths.
 */
export interface StyleRecipe {
  id: number;
  name: string;
  description: string;
  features: {
    [k: string]: unknown;
  };
  reference_count: number;
  created_at: string;
}
/**
 * What a Pro Edit is estimated to cost before it runs (SPEC-v3 1.6):
 * the LLM tokens and USD (None: no price set) of the Director and of the
 * critic at most (every round, every retry), the text the dialog shows,
 * the monthly cap and this month's spend (USD), and whether the cap
 * already blocks the LLM (the rule-based Director then plans).
 */
export interface ProEditEstimate {
  director_tokens: number;
  director_usd: number | null;
  critic_tokens: number;
  critic_usd: number | null;
  critic_rounds: number;
  text: string;
  monthly_cap_usd: number | null;
  month_spend_usd: number;
  blocked: boolean;
}
/**
 * PATCH /proedit/clips/{id}/plan: the edit decisions of the new plan
 * version (the editor's; each becomes a manual item).
 */
export interface ProEditItemsUpdate {
  /**
   * @maxItems 500
   */
  items: EdlItem[];
}
/**
 * What the owner chose for a Pro Edit (SPEC-v3 3.8): the preset and
 * intensity, the style recipe to aim for, the music ("auto": the preset's
 * pick of the bundled loops; "none"; or a catalog music asset: a library
 * asset id or a bundled loop's name), whether the critic runs and whether
 * the edit ends on a loop-friendly ending (its last frames and sound blend
 * into its opening; a style recipe whose references loop asks for it
 * too). The subject cut-out (proedit/segment.py; skipped, with the reason
 * logged, when its engine is not installed) puts the subject in front of
 * overlays and captions (subject_front) and blurs the background or swaps
 * it for background_color (background).
 */
export interface ProEditOptions {
  preset:
    | "clean_pro"
    | "dark_edit"
    | "phonk_edit"
    | "cinematic"
    | "skull_moment"
    | "glitch";
  intensity: "clean" | "standard" | "pro" | "extreme";
  style_recipe_id: number | null;
  music: string;
  use_critic: boolean;
  loop_ending: boolean;
  subject_front: boolean;
  background: "keep" | "blur" | "swap";
  background_color: string;
}
/**
 * The plan of a Pro Edit variant of clip clip_id (SPEC-v3 3.1): version
 * counts the plans of the clip from 1 (a new version for each change that
 * keeps the one before), items are its edit decisions and rationale is the
 * director's summary. style_recipe_id is the StyleRecipe it aims for.
 */
export interface ProEditPlan {
  id: number;
  clip_id: number;
  preset:
    | "clean_pro"
    | "dark_edit"
    | "phonk_edit"
    | "cinematic"
    | "skull_moment"
    | "glitch";
  intensity: "clean" | "standard" | "pro" | "extreme";
  style_recipe_id: number | null;
  version: number;
  items: EdlItem[];
  rationale: string;
  created_by: "director" | "rule_director" | "user" | "critic_revision";
}
/**
 * One run of Pro Edit on clip clip_id (SPEC-v3 6): the plan it made
 * (None until it has one), how many critic rounds ran and their scores,
 * the cost in US dollars as estimated before and as spent (None: no LLM
 * call), and when it started and finished; error says why a failed run
 * failed. job_id is the job that runs it (its progress and ETA), mode what
 * it does, options the owner's choices (None for runs made before them)
 * and notes the messages the UI shows (why the rule-based Director made
 * the plan, why the critic stopped).
 */
export interface ProEditRun {
  id: number;
  clip_id: number;
  plan_id: number | null;
  status: "queued" | "running" | "done" | "failed";
  rounds: number;
  critic_scores: CriticRound[];
  cost_estimate: number | null;
  cost_actual: number | null;
  started_at: string | null;
  finished_at: string | null;
  error: string | null;
  job_id: number | null;
  mode: "start" | "regenerate" | "critic" | "render";
  options: ProEditOptions | null;
  notes: string[];
}
/**
 * A Pro Edit run that was queued: the clip it edits (the new variant
 * for a start), the run and its job.
 */
export interface ProEditStarted {
  clip: Clip;
  run: ProEditRun;
  job_id: number;
}
/**
 * GET /proedit/status: Pro Edit is available (proedit.enabled); when it
 * is off the endpoint answers 404 proedit_disabled instead.
 * critic_max_rounds is N of the progress's "critic round n/N" (0: the
 * critic is off).
 */
export interface ProEditStatus {
  enabled: boolean;
  critic_max_rounds: number;
}
/**
 * GET /proedit/clips/{id}/timing: what the Pro Edit editor snaps a
 * dragged item to (SPEC-v3 3.1): the render's frame rate, the rendered
 * clip's length, its words and the beats of its plan's music beds, all in
 * seconds of the rendered clip.
 */
export interface ProEditTiming {
  fps: number;
  duration: number;
  words: ProEditWord[];
  beats: number[];
}
/**
 * A word of a clip, from start to end seconds of the rendered clip.
 */
export interface ProEditWord {
  text: string;
  start: number;
  end: number;
}
/**
 * A named set of processing settings that the user saved ("My
 * presets"); like the saved default, it holds no timeframe or subtitles,
 * which belong to one video.
 */
export interface ProcessingPreset {
  name: string;
  settings: ProcessingSettings;
}
/**
 * The body of PUT /projects/{id}/campaign: the campaign whose preset the
 * project and its clips get (null: the project leaves its campaign and
 * keeps its settings).
 */
export interface ProjectCampaign {
  campaign_id: number | null;
}
/**
 * The body of POST /projects: a video URL, how to process it and, if the
 * owner says so now, why they may use it (SPEC-v2 1.6).
 */
export interface ProjectCreate {
  url: string;
  settings?: ProcessingSettings;
  source_rights?:
    ("own" | "permission" | "cc_by" | "public_domain" | "other") | null;
  credit_line?: string;
}
/**
 * The body of PATCH /projects/{id}: the brand template of the project's
 * clips (null: none), its source rights (null: unset), credit line and
 * title (the owner's name for it; not blank).
 *
 * Only the fields that are sent change; at least one must be sent.
 */
export interface ProjectPatch {
  brand_template_id?: number | null;
  source_rights?:
    ("own" | "permission" | "cc_by" | "public_domain" | "other") | null;
  credit_line?: string;
  title?: string;
}
/**
 * The disk space one project uses (GET /storage), in bytes: its uploaded
 * source video, the work files of its jobs and its output (rendered clips,
 * exports, previews); cleanable is the share of work and preview files
 * that "Clean up" deletes.
 */
export interface ProjectStorage {
  project_id: number;
  title: string;
  status: "queued" | "running" | "done" | "failed";
  archived_at: string | null;
  source_bytes: number;
  work_bytes: number;
  output_bytes: number;
  cleanable_bytes: number;
  /**
   * Everything the project uses on disk (read-only).
   */
  total_bytes: number;
}
/**
 * The month's total of one kind for one project; project_id is None for
 * use outside a project (or of a deleted one).
 */
export interface ProjectUsage {
  project_id: number | null;
  kind: string;
  units: number;
  cost_usd: number | null;
}
/**
 * The body of POST /clips/{id}/quick-post: the platforms to post to
 * (each one's default account), the accounts that replace a platform's
 * default (their platform is posted to even if left out of platforms) and
 * what the post says on each platform (left out: written by the AI).
 */
export interface QuickPost {
  /**
   * @maxItems 4
   */
  platforms?: (
    "youtube" | "tiktok" | "instagram" | "facebook" | "x" | "linkedin"
  )[];
  /**
   * @maxItems 50
   */
  account_ids?: number[];
  texts?: {
    [k: string]: PostText;
  };
}
/**
 * A reference after an analysis run: its row and the reason it could
 * not be analyzed (None when it was).
 */
export interface ReferenceResult {
  reference: StyleReference;
  error: string | null;
}
/**
 * A reference link of a style recipe: when its media was analyzed and
 * when that media was deleted (SPEC-v3 4.2), and when the owner confirmed
 * that they may use it (4.1).
 */
export interface StyleReference {
  id: number;
  recipe_id: number;
  url: string;
  analyzed_at: string | null;
  deleted_at: string | null;
  rights_confirmed_at: string;
}
/**
 * A genre reframing preset (GET /reframe-presets), the layout and the
 * tracking parameters reframe uses for it (pipeline/reframe_presets).
 *
 * layout: the layout of every clip (None: split when two faces persist,
 * else fill). split_share: the share of a clip's samples that need two
 * faces for split. camera_motion: the camera motion that picking the
 * preset sets (pipeline/camera_motion). objects: follow a moving object
 * in shots without a face.
 */
export interface ReframePresetInfo {
  name: "podcast-2" | "standup" | "gaming" | "vlog";
  label: string;
  description: string;
  layout:
    | (
        | "fill"
        | "fit"
        | "split"
        | "grid"
        | "pip"
        | "screenshare"
        | "gameplay"
        | "square_blur"
      )
    | null;
  split_share: number;
  camera_motion: "calm" | "normal" | "fast";
  objects: boolean;
}
/**
 * The body of POST /projects/{id}/replace-everywhere: change the words
 * find (whole words, any case) into replace in the project's transcript and
 * clips; remember also adds it to the vocabulary's corrections.
 */
export interface ReplaceRequest {
  find: string;
  replace: string;
  remember: boolean;
}
/**
 * What replace-everywhere changed: the places in the transcript, and
 * the clips whose texts or caption words changed.
 */
export interface ReplaceResult {
  transcript_matches: number;
  clips_changed: number;
}
/**
 * The body of POST /projects/{id}/reprompt: the new prompt-to-clip
 * request (not blank), applied to the project's existing transcript.
 */
export interface RepromptRequest {
  prompt: string;
}
/**
 * The crop keyframes that follow a tracked subject through a scene
 * (pipeline/click_track), and the seed with the box that was tracked.
 */
export interface SceneTrack {
  keyframes: CropPoint[];
  seed: TrackSeed;
}
/**
 * A scene to track (POST /clips/{id}/scenes/track): start to end
 * seconds of the source, and the box (or click: no size) around the
 * subject to follow.
 */
export interface SceneTrackRequest {
  start: number;
  end: number;
  seed: TrackSeed;
}
/**
 * A clip candidate with its virality scores (SPEC 6.6).
 */
export interface ScoredCandidate {
  start: number;
  end: number;
  title: string;
  hook_text: string;
  description: string;
  /**
   * @minItems 3
   * @maxItems 8
   */
  hashtags: [string, string, string, ...string[]];
  emphasis_words: string[];
  reason: string;
  hook: number;
  flow: number;
  value: number;
  trend: number;
  scores: Scores;
}
/**
 * Scored clip candidates as {"clips": [...]}, best overall score first:
 * the content of scored.json (SPEC 6.6) and snapped.json (SPEC 6.7).
 */
export interface ScoredList {
  clips: ScoredCandidate[];
}
/**
 * Where a search term sits in a hit's text: from the character start up
 * to, not including, end.
 */
export interface SearchHighlight {
  start: number;
  end: number;
}
/**
 * One transcript segment of a library search (GET /search): where it is
 * (project_id, and start, the second of the video where the first matching
 * word is said), the whole segment's text with the matches marked, and how
 * well it matches (rank: lower is better; BM25).
 */
export interface SearchHit {
  project_id: number;
  project_title: string;
  segment_id: number;
  start: number;
  segment_start: number;
  end: number;
  text: string;
  highlights: SearchHighlight[];
  rank: number;
}
/**
 * The body of POST /clips/{id}/sections: a part of the source to add
 * to the clip as a section, played at index of the clip's sections (0:
 * first; null: last). It may not overlap another section.
 */
export interface SectionAdd {
  start: number;
  end: number;
  index: number | null;
}
/**
 * The body of POST /clips/{id}/sections/reorder: the clip's sections'
 * current indices in their new play order (each index once).
 */
export interface SectionOrder {
  /**
   * @minItems 1
   */
  order: [number, ...number[]];
}
/**
 * The body of PUT /clips/{id}/sections/{index} (SPEC-v2 3.5 trim or
 * extend a section): its new start and end in seconds of the source. The
 * API clamps them to the source and to the sections next to it there.
 */
export interface SectionSpan {
  start: number;
  end: number;
}
/**
 * The body of POST /clips/{id}/sections/split: split the section that
 * plays the source at at seconds into two at that time.
 */
export interface SectionSplit {
  at: number;
}
/**
 * A transcript segment made of timed words.
 */
export interface Segment {
  id: number;
  start: number;
  end: number;
  text: string;
  words: Word[];
  speaker: string;
}
/**
 * The PUT body: the settings to change. An empty ffmpeg_bin or
 * ffprobe_bin means the default tool; an empty key, browser or cookies
 * file clears it; always_hashtags [] clears them. A usage cap of 0 means
 * no cap. video_encoder must be one that ffmpeg has. An empty smtp_host
 * turns email notifications off, an empty digest_time the daily digest.
 */
export interface SettingsUpdate {
  llm_provider?:
    ("copilot" | "openai" | "ollama" | "anthropic" | "claude_code") | null;
  llm_model?: string | null;
  openai_base_url?: string | null;
  ollama_host?: string | null;
  openai_api_key?: string | null;
  github_copilot_token?: string | null;
  copilot_account?: string | null;
  anthropic_api_key?: string | null;
  anthropic_base_url?: string | null;
  anthropic_model?: string | null;
  claude_code_bin?: string | null;
  claude_code_model?: string | null;
  whisper_model?: string | null;
  transcribe_backend?: ("auto" | "faster_whisper" | "mlx") | null;
  credit_template?: string | null;
  always_hashtags?: string[] | null;
  post_missed_policy?: ("post_late" | "skip") | null;
  models_dir?: string | null;
  ffmpeg_bin?: string | null;
  ffprobe_bin?: string | null;
  video_encoder?: ("libx264" | "h264_videotoolbox") | null;
  ytdlp_cookies_from_browser?: string | null;
  ytdlp_cookies_file?: string | null;
  usage_cap_compute_hours?: number | null;
  usage_cap_llm_tokens?: number | null;
  usage_cap_api_calls?: number | null;
  smtp_host?: string | null;
  smtp_port?: number | null;
  smtp_user?: string | null;
  smtp_password?: string | null;
  smtp_from?: string | null;
  notify_email_to?: string | null;
  desktop_notifications?: boolean | null;
  quota_warn_percent?: number | null;
  digest_time?: string | null;
}
/**
 * The settings as GET /api/settings returns them.
 */
export interface SettingsView {
  llm_provider: "copilot" | "openai" | "ollama" | "anthropic" | "claude_code";
  llm_model: string;
  openai_base_url: string;
  ollama_host: string;
  openai_api_key_set: boolean;
  github_copilot_token_set: boolean;
  copilot_account: string;
  anthropic_api_key_set: boolean;
  anthropic_base_url: string;
  anthropic_model: string;
  claude_code_bin: string;
  claude_code_model: string;
  whisper_model: string;
  transcribe_backend: "auto" | "faster_whisper" | "mlx";
  transcribe_backend_active: "faster_whisper" | "mlx";
  credit_template: string;
  always_hashtags: string[];
  post_missed_policy: "post_late" | "skip";
  models_dir: string;
  ffmpeg_bin: string;
  ffprobe_bin: string;
  video_encoder: "libx264" | "h264_videotoolbox";
  video_encoders: ("libx264" | "h264_videotoolbox")[];
  ytdlp_cookies_from_browser: string;
  ytdlp_cookies_file: string;
  usage_cap_compute_hours: number;
  usage_cap_llm_tokens: number;
  usage_cap_api_calls: number;
  smtp_host: string;
  smtp_port: number;
  smtp_user: string;
  smtp_password_set: boolean;
  smtp_from: string;
  notify_email_to: string;
  desktop_notifications: boolean;
  quota_warn_percent: number;
  digest_time: string;
  data_dir: string;
}
/**
 * A sound effect that the LLM wants at a moment of a clip: its number in
 * the numbered moments of the prompt (from 0) and tags that describe the
 * sound (searched in the pack).
 */
export interface SfxPick {
  moment: number;
  /**
   * @minItems 1
   * @maxItems 4
   */
  tags: [string, ...string[]];
}
/**
 * The LLM's reply with the sound effects of a clip (none if it needs
 * none).
 */
export interface SfxReply {
  /**
   * @maxItems 8
   */
  sounds: SfxPick[];
}
/**
 * A sound effect of the bundled pack (assets/sfx; pipeline/sfx): its
 * library asset, title, tags to search by and length in seconds (None if
 * ffprobe cannot read the file).
 */
export interface SfxSound {
  asset: Asset;
  title: string;
  duration: number | null;
  tags: string[];
}
/**
 * An audio or video event detected in the source.
 */
export interface SignalEvent {
  kind:
    | "laugh"
    | "applause"
    | "cheer"
    | "music"
    | "scene_cut"
    | "silence"
    | "energy_peak";
  start: number;
  end: number;
  intensity: number;
}
/**
 * A social account the owner connected with the platform's OAuth sign-in
 * (SPEC-v2 3.10, 4); a platform may have several. token_ref names the
 * account's token in the encrypted token store (the token never enters the
 * database); scopes are the ones the platform granted; restrictions are
 * the platform's limits on this account or app that the UI shows (e.g.
 * "unaudited app: posts are private"). is_default marks the account that
 * a one-click post uses on its platform (one per platform); avatar_url is
 * the picture the platform gave at sign-in; always_hashtags are the hashtags
 * (without "#") that every generated post to the account carries.
 */
export interface SocialAccount {
  id: number;
  platform: "youtube" | "tiktok" | "instagram" | "facebook" | "x" | "linkedin";
  external_id: string;
  display_name: string;
  token_ref: string;
  scopes: string[];
  connected_at: string;
  restrictions: string[];
  is_default: boolean;
  avatar_url: string | null;
  always_hashtags: string[];
}
/**
 * The title, duration (seconds) and thumbnail of a linked video; each is
 * None when the page does not say.
 */
export interface SourceInfo {
  url: string;
  title: string | null;
  duration: number | null;
  thumbnail_url: string | null;
}
/**
 * What ingest learned about a source video; stored as meta.json (SPEC 6.1).
 *
 * Later steps only consider the [timeframe_start, timeframe_end] seconds of
 * the source. channel and channel_url name the uploader of a downloaded
 * video (for the credit line); they are None for local files.
 */
export interface SourceMeta {
  title: string;
  duration: number;
  width: number;
  height: number;
  fps: number;
  timeframe_start: number;
  timeframe_end: number;
  channel: string | null;
  channel_url: string | null;
}
/**
 * The body of POST /sources/probe: the video link to read.
 */
export interface SourceProbe {
  url: string;
}
/**
 * The body of PUT /clips/{id}/enhance: how strongly the render cleans the
 * clip's speech, 0 (off) to 1 (strongest; pipeline/enhance).
 */
export interface SpeechEnhance {
  strength: number;
}
/**
 * A language that Whisper transcribes: its code and English name.
 */
export interface SpeechLanguage {
  code: string;
  name: string;
}
/**
 * Whether a stock provider can be used: when it cannot (no API key),
 * message says which setting to fill in.
 */
export interface StockProviderStatus {
  provider: "pexels" | "pixabay";
  label: string;
  enabled: boolean;
  message: string;
}
/**
 * What POST /projects/{id}/cleanup or /archive did: the bytes it freed
 * and the project's disk use now.
 */
export interface StorageCleanup {
  freed_bytes: number;
  storage: ProjectStorage;
}
/**
 * GET /storage: every project's disk use, largest first, their sum and
 * the free space on the disk of the data directory.
 */
export interface StorageReport {
  projects: ProjectStorage[];
  total_bytes: number;
  free_bytes: number;
  data_dir: string;
}
/**
 * How close a Pro Edit's video is to a style recipe (SPEC-v3 4.4): the
 * score 0-100 (None when it measured none of the recipe's metrics) and
 * each metric compared, for the video measured at measured_at.
 */
export interface StyleMatch {
  clip_id: number;
  recipe_id: number;
  recipe_name: string;
  score: number | null;
  metrics: StyleMetricMatch[];
  measured_at: string;
}
/**
 * One metric of a style-match: the value measured on the Pro Edit, the
 * recipe's target and how well it fits (1 inside the range).
 */
export interface StyleMetricMatch {
  key: string;
  label: string;
  unit: string;
  value: number;
  target: StyleTarget;
  score: number;
}
/**
 * A metric's target in a style recipe: the median over the references
 * that measured it, the range [low, high] across them and how many did
 * (0 when it was set by hand or imported).
 */
export interface StyleTarget {
  median: number;
  low: number;
  high: number;
  count: number;
}
/**
 * A number of a style recipe (SPEC-v3 4.4): its key, label, unit and
 * group, the bounds and step of its slider in the recipe editor, and its
 * tolerance: the least width of the range a measured value is scored
 * against (proedit/style/recipe.style_match).
 */
export interface StyleMetric {
  key: string;
  label: string;
  unit: string;
  group:
    | "rhythm"
    | "motion"
    | "look"
    | "effects"
    | "captions"
    | "audio"
    | "structure";
  min: number;
  max: number;
  step: number;
  tolerance: number;
}
/**
 * A new recipe: its name, its reference links and the rights
 * confirmation, which must be true.
 */
export interface StyleRecipeCreate {
  name: string;
  /**
   * @minItems 1
   * @maxItems 5
   */
  urls: [string, ...string[]];
  rights_confirmed: true;
}
/**
 * A recipe with its references and its targets.
 */
export interface StyleRecipeDetail {
  recipe: StyleRecipe;
  references: ReferenceResult[];
  targets: StyleTargets;
}
/**
 * What a style recipe aims for: a target per metric key (StyleMetric)
 * and the caption fill color (the median RGB of the references').
 */
export interface StyleTargets {
  metrics: {
    [k: string]: StyleTarget;
  };
  caption_color: string | null;
}
/**
 * A style recipe as an exported JSON file (SPEC-v3 4.5): its name,
 * description, the number of references its targets come from and the
 * targets. It never holds media, media paths or links; importing it
 * makes a new recipe without references.
 */
export interface StyleRecipeExport {
  format: "clipforge.style_recipe";
  version: 1;
  name: string;
  description: string;
  reference_count: number;
  targets: StyleTargets;
}
/**
 * An edit of a style recipe from its editor: a new name, description
 * or targets (the sliders); a field left out keeps its value.
 */
export interface StyleRecipePatch {
  name?: string | null;
  description?: string | null;
  targets?: StyleTargets | null;
}
/**
 * What the recipe form shows: the terms notice that goes with the
 * rights checkbox and the limits of a reference.
 */
export interface StyleTerms {
  notice: string;
  max_links: number;
  max_seconds: number;
  max_height: number;
}
/**
 * The owner's record of submitting one published post on the board of
 * its campaign (SPEC-v2 3.18); the owner submits by hand and ticks it
 * here. Made (not_submitted) when the published post is first listed.
 * submitted_at is when it was ticked; approved_views and payout_usd are
 * what the campaign board reported, entered by the owner; answered_at is
 * when they were last entered. campaign_id is None once its campaign was
 * deleted (the record stays).
 */
export interface Submission {
  id: number;
  post_id: number;
  campaign_id: number | null;
  submitted_at: string | null;
  status: "not_submitted" | "submitted" | "approved" | "rejected" | "paid";
  approved_views: number | null;
  payout_usd: number | null;
  notes: string;
  answered_at: string | null;
}
/**
 * The body of PATCH /submissions/{id}: the fields that are sent change
 * (null clears approved_views, payout_usd; status moves along
 * clipforge.submissions.TRANSITIONS, 409 otherwise); at least one.
 */
export interface SubmissionPatch {
  status:
    ("not_submitted" | "submitted" | "approved" | "rejected" | "paid") | null;
  approved_views: number | null;
  payout_usd: number | null;
  notes: string | null;
}
/**
 * A submission with what the tracker shows of its post and campaign:
 * the post's platform, URL and clip, the campaign's name, and copy_text,
 * the post URL with the campaign's required information, ready to paste
 * into the campaign board (read-only).
 */
export interface SubmissionView {
  id: number;
  post_id: number;
  campaign_id: number | null;
  submitted_at: string | null;
  status: "not_submitted" | "submitted" | "approved" | "rejected" | "paid";
  approved_views: number | null;
  payout_usd: number | null;
  notes: string;
  answered_at: string | null;
  platform: "youtube" | "tiktok" | "instagram" | "facebook" | "x" | "linkedin";
  post_url: string;
  clip_id: number;
  clip_title: string;
  campaign_name: string | null;
  copy_text: string;
}
/**
 * The reply of POST /subtitles: the token that
 * ProcessingSettings.subtitles_id takes, and the file's cue count.
 */
export interface SubtitlesUpload {
  subtitles_id: string;
  cues: number;
}
/**
 * The props of a text item (a text overlay): text in font (a bundled or
 * uploaded font), size times the frame's height tall, in color, outlined
 * in stroke (stroke_width times the font size wide) if stroke is set, on
 * a box of color box at box_opacity if box is set, centered at (x, y) in
 * fractions of the frame. It comes in with animation_in over in_seconds
 * from the item's start and goes out with animation_out over out_seconds
 * up to its end (pipeline/text_overlay).
 */
export interface TextProps {
  text: string;
  font: string;
  size: number;
  color: string;
  stroke: string | null;
  stroke_width: number;
  box: string | null;
  box_opacity: number;
  x: number;
  y: number;
  animation_in:
    | "none"
    | "fade"
    | "slide_up"
    | "slide_down"
    | "slide_left"
    | "slide_right"
    | "pop";
  animation_out:
    | "none"
    | "fade"
    | "slide_up"
    | "slide_down"
    | "slide_left"
    | "slide_right"
    | "pop";
  in_seconds: number;
  out_seconds: number;
}
/**
 * The body of POST /clips/{id}/thumbnail/apply: the cover (an image
 * asset) for every draft and queued post of the clip.
 */
export interface ThumbnailApply {
  asset_id: number;
}
/**
 * The body of POST /clips/{id}/thumbnail: the moment of the clip's
 * rendered video, in seconds from its start, to use as the cover.
 */
export interface ThumbnailFrame {
  time_s: number;
}
/**
 * The payload of a TikTok post (SPEC-v2 3.10, TikTok's Direct Post
 * rules). privacy_level has no default: the user picks one of the
 * account's options (unaudited apps: SELF_ONLY only). Comments, Duets
 * and Stitches stay off unless allowed. caption defaults to the clip's
 * title + hashtags; cover_timestamp_ms picks the cover frame.
 * brand_organic (promotes the creator's own business) and branded_content
 * (paid partnership, never private) are the commercial content
 * disclosure; ai_generated labels AI-generated content. Keys of other
 * platforms are ignored.
 */
export interface TikTokPostOptions {
  caption: string | null;
  privacy_level:
    | (
        | "PUBLIC_TO_EVERYONE"
        | "MUTUAL_FOLLOW_FRIENDS"
        | "FOLLOWER_OF_CREATOR"
        | "SELF_ONLY"
      )
    | null;
  allow_comment: boolean;
  allow_duet: boolean;
  allow_stitch: boolean;
  cover_timestamp_ms: number | null;
  brand_organic: boolean;
  branded_content: boolean;
  ai_generated: boolean;
}
/**
 * The body of PATCH /clips/{id}/tracks: the tracks to replace (unset or
 * null tracks are kept). The video track follows the clip's segments, so
 * it is not here.
 */
export interface TimelinePatch {
  broll: TrackItem[] | null;
  overlays: TrackItem[] | null;
  text: TrackItem[] | null;
  music: TrackItem[] | null;
  sfx: TrackItem[] | null;
  voiceover: TrackItem[] | null;
}
/**
 * The body of POST /projects/{id}/clip-by-topic: the ids of the chapters
 * to clip (at least one, each once) and, optionally, a prompt-to-clip
 * request that applies within them.
 */
export interface TopicClipRequest {
  /**
   * @minItems 1
   */
  chapters: [number, ...number[]];
  prompt: string | null;
}
/**
 * The full transcript of a source video.
 */
export interface Transcript {
  language: string;
  duration: number;
  segments: Segment[];
  approximate_times: boolean;
}
/**
 * One cue as the LLM translates it: its number in the numbered cues
 * that the prompt lists (from 0) and its text in the target language.
 */
export interface TranslatedCue {
  index: number;
  text: string;
}
/**
 * The reply to the caption translation prompt, {"cues": [...]}.
 */
export interface TranslatedCues {
  cues: TranslatedCue[];
}
/**
 * A voice of an installed TTS engine (GET /api/voices): id is
 * "<engine>:<voice>" (a Piper voice with several speakers:
 * "piper:<voice>:<speaker>"), name what the UI shows, language a
 * BCP 47 tag, gender if the engine says, and the license of the voice
 * model.
 */
export interface TtsVoice {
  id: string;
  engine: "kokoro" | "piper";
  name: string;
  language: string;
  gender: ("female" | "male") | null;
  license: string;
}
/**
 * The body of POST /uploads/{id}/complete: how to process the video and
 * its source rights, as in ProjectCreate.
 */
export interface UploadComplete {
  settings?: ProcessingSettings;
  source_rights?:
    ("own" | "permission" | "cc_by" | "public_domain" | "other") | null;
  credit_line?: string;
}
/**
 * The body of POST /uploads: the file's name and its size in bytes (at
 * most 30 GB).
 */
export interface UploadCreate {
  filename: string;
  size: number;
}
/**
 * An upload: its id, file name, size and the bytes received so far (the
 * offset of the next chunk).
 */
export interface UploadSession {
  id: string;
  filename: string;
  size: number;
  offset: number;
}
/**
 * A measured use of compute or a paid service (SPEC-v2 2.4): units of
 * its kind (seconds, tokens, calls) and the cost in USD if it is paid.
 * project_id is None for use outside a project.
 */
export interface UsageRecord {
  id: number;
  project_id: number | null;
  kind: string;
  units: number;
  cost_usd: number | null;
  at: string;
}
/**
 * GET /api/usage: the month ("YYYY-MM"), its totals per kind (every
 * metered kind, then any other recorded) and per project and kind.
 */
export interface UsageSummary {
  month: string;
  kinds: KindUsage[];
  projects: ProjectUsage[];
}
/**
 * The brand vocabulary (SPEC-v2 3.4): terms Whisper is told to expect
 * (its hotwords), and corrections {heard: correct} that every transcript
 * gets after transcription. A correction matches whole words, any case.
 */
export interface Vocabulary {
  /**
   * @maxItems 100
   */
  terms: string[];
  corrections: {
    [k: string]: string;
  };
}
/**
 * The body of POST /clips/{id}/voiceover: text that voice speaks at
 * speed, put on the voiceover track from start seconds of the rendered
 * clip at volume, ducking the clip's sound if duck.
 */
export interface VoiceoverCreate {
  text: string;
  voice: string;
  start: number;
  speed: number;
  volume: number;
  duck: boolean;
}
/**
 * The body of PATCH /clips/{id}/voiceover/{item_id}: what to change
 * (unset fields are kept). New text, voice or speed speaks it again;
 * start moves it.
 */
export interface VoiceoverPatch {
  text: string | null;
  voice: string | null;
  start: number | null;
  speed: number | null;
  volume: number | null;
  duck: boolean | null;
}
/**
 * The props of a voiceover item (SPEC-v2 3.5, pipeline/voiceover): an
 * AudioProps; text, voice (a TtsVoice id) and speed when a TTS voice
 * spoke it (None for a recording from the media library), and, if duck,
 * the clip's own sound is lowered while the item plays.
 */
export interface VoiceoverProps {
  volume: number;
  offset: number;
  text: string | null;
  voice: string | null;
  speed: number;
  duck: boolean;
}
/**
 * An alert of the watch: a new upload (kind "upload", project_id is its
 * project) or a stream that went live (kind "live"). published_at is when
 * the source says it was published (or went live), detected_at when
 * ClipForge saw it, via how (push or poll). external_id is the video or
 * stream id.
 */
export interface WatchEvent {
  id: number;
  platform: "youtube" | "twitch";
  kind: "upload" | "live";
  external_id: string;
  source_name: string;
  title: string;
  url: string;
  project_id: number | null;
  published_at: string | null;
  detected_at: string;
  via: "push" | "poll";
}
/**
 * The watch's setup (GET /watch/status). push_available: a public
 * callback URL is set, so YouTube and Twitch can push (else everything is
 * polled); poll_interval_s: the polling interval; twitch_configured: the
 * Twitch app keys are set (go-live needs them); handles_supported: the
 * YouTube API key is set, so a channel can be added by @handle.
 */
export interface WatchStatus {
  push_available: boolean;
  poll_interval_s: number;
  twitch_configured: boolean;
  handles_supported: boolean;
}
/**
 * A YouTube channel that Auto Import watches (SPEC-v2 3.1): its new
 * videos become projects with these settings, source rights and credit
 * line. auto_schedule_drafts asks for the clips to be scheduled as drafts
 * (the scheduler task wires it). last_checked_at is the time of the last
 * feed read that worked (None: never, so the videos already in the feed
 * are not imported); last_error is the error of the latest read that
 * failed, None once a read works again.
 */
export interface WatchedChannel {
  id: number;
  channel_id: string;
  title: string;
  settings: ProcessingSettings;
  source_rights:
    ("own" | "permission" | "cc_by" | "public_domain" | "other") | null;
  credit_line: string;
  auto_schedule_drafts: boolean;
  enabled: boolean;
  last_checked_at: string | null;
  last_error: string | null;
  created_at: string;
  push_state:
    "off" | "pending" | "subscribed" | "denied" | "failed" | "revoked";
  push_lease_expires_at: string | null;
  push_requested_at: string | null;
  push_error: string | null;
  campaign_id: number | null;
}
/**
 * What adding a channel to Auto Import takes: the channel (id, @handle
 * or link) and the defaults of the projects of its new videos.
 */
export interface WatchedChannelCreate {
  channel: string;
  settings?: ProcessingSettings;
  source_rights?:
    ("own" | "permission" | "cc_by" | "public_domain" | "other") | null;
  credit_line?: string;
  auto_schedule_drafts?: boolean;
}
/**
 * The body of PATCH /auto-import/channels/{id}: the defaults of the
 * channel's new projects and whether it is watched (enabled).
 *
 * Only the fields that are sent change (source_rights null: unset); at
 * least one must be sent.
 */
export interface WatchedChannelPatch {
  settings?: ProcessingSettings;
  source_rights?:
    ("own" | "permission" | "cc_by" | "public_domain" | "other") | null;
  credit_line?: string;
  auto_schedule_drafts?: boolean;
  enabled?: boolean;
}
/**
 * A Twitch streamer whose go-live the watch reports (T28c). user_id is
 * the broadcaster id (None until resolved); push_state is its EventSub
 * stream.online subscription (subscription_id at Twitch), else it is
 * polled. live_since is set while a poll sees the stream live;
 * last_live_at is when the latest live stream started.
 */
export interface WatchedStreamer {
  id: number;
  login: string;
  user_id: string | null;
  display_name: string;
  enabled: boolean;
  push_state:
    "off" | "pending" | "subscribed" | "denied" | "failed" | "revoked";
  push_requested_at: string | null;
  push_error: string | null;
  subscription_id: string | null;
  live_since: string | null;
  last_live_at: string | null;
  last_checked_at: string | null;
  last_error: string | null;
  created_at: string;
}
/**
 * What watching a Twitch streamer takes: a login or twitch.tv link.
 */
export interface WatchedStreamerCreate {
  login: string;
}
/**
 * The body of PATCH /watch/streamers/{id}: whether it is watched.
 */
export interface WatchedStreamerPatch {
  enabled: boolean;
}
/**
 * A video that Auto Import saw in a watched channel's feed. project_id
 * is the project made for it; None for the videos that were already in the
 * feed when the channel was added.
 */
export interface WatchedVideo {
  watched_channel_id: number;
  video_id: string;
  title: string;
  published_at: string | null;
  project_id: number | null;
  seen_at: string;
}
/**
 * The audio level of a span of the source: peaks[i] is the loudest
 * sample (0-1 of full scale) from start + i / peaks_per_second seconds on,
 * for 1 / peaks_per_second seconds.
 */
export interface Waveform {
  start: number;
  end: number;
  peaks_per_second: number;
  peaks: number[];
}
/**
 * A webhook (SPEC-v2 3.14, 4): ClipForge POSTs each of its events to
 * url, signed with the webhook's secret (HMAC-SHA256). The secret is
 * shown once, when the webhook is made (WebhookCreated).
 */
export interface Webhook {
  id: number;
  url: string;
  events: (
    "project.completed" | "clip.rendered" | "post.published" | "post.failed"
  )[];
  enabled: boolean;
  created_at: string;
}
/**
 * Body of POST /webhooks.
 */
export interface WebhookCreate {
  url: string;
  /**
   * @minItems 1
   */
  events: [
    "project.completed" | "clip.rendered" | "post.published" | "post.failed",
    ...(
      "project.completed" | "clip.rendered" | "post.published" | "post.failed"
    )[],
  ];
}
/**
 * A webhook just made: secret signs its deliveries; shown this once.
 */
export interface WebhookCreated {
  id: number;
  url: string;
  events: (
    "project.completed" | "clip.rendered" | "post.published" | "post.failed"
  )[];
  enabled: boolean;
  created_at: string;
  secret: string;
}
/**
 * One event sent (or to be sent) to one webhook, with its log: the
 * attempts, the last answer's HTTP status and the last error. data is the
 * event's payload (the "data" of the body that is sent).
 */
export interface WebhookDelivery {
  id: number;
  webhook_id: number;
  event:
    "project.completed" | "clip.rendered" | "post.published" | "post.failed";
  data: {
    [k: string]: unknown;
  };
  status: "pending" | "delivered" | "failed";
  attempts: number;
  created_at: string;
  attempted_at: string | null;
  next_attempt_at: string | null;
  response_status: number | null;
  error: string | null;
}
/**
 * Body of PATCH /webhooks/{id}: the fields to change.
 */
export interface WebhookUpdate {
  url: string | null;
  events:
    | [
        (
          | "project.completed"
          | "clip.rendered"
          | "post.published"
          | "post.failed"
        ),
        ...(
          | "project.completed"
          | "clip.rendered"
          | "post.published"
          | "post.failed"
        )[],
      ]
    | null;
  enabled: boolean | null;
}
/**
 * One word of a clip's captions as the LLM marks it: its number in the
 * numbered words that the prompt lists (from 0), whether it is an emphasis
 * word, and the emoji that follows it ("" for none).
 */
export interface WordMark {
  index: number;
  emphasis: boolean;
  emoji: string | "";
}
/**
 * The words the LLM marks, {"marks": [...]}: the reply to the caption
 * emphasis prompt (pipeline/caption_emphasis).
 */
export interface WordMarks {
  marks: WordMark[];
}
/**
 * The payload of a YouTube post (SPEC-v2 3.10). title, description and
 * tags default to the clip's title, description + hashtags and hashtags;
 * category_id is a YouTube video category ("22": People & Blogs). A
 * public post with a future scheduled_at is uploaded private with
 * YouTube's publishAt; made_for_kids and synthetic_media are the
 * channel owner's declarations (child-directed; realistic altered or
 * synthetic content). Keys of other platforms are ignored.
 */
export interface YouTubePostOptions {
  title: string | null;
  description: string | null;
  tags: string[] | null;
  category_id: string;
  privacy: "public" | "unlisted" | "private";
  made_for_kids: boolean;
  synthetic_media: boolean;
  notify_subscribers: boolean;
}
/**
 * The body of PUT /projects/{id}/zoom-out: the zoom-out moments
 * intensity to save for the project and apply to its clips.
 */
export interface ZoomOutRequest {
  intensity: "off" | "subtle" | "balanced" | "frequent";
}
/**
 * The answer to PUT /projects/{id}/zoom-out: the project with the
 * saved intensity and the ids of the clips whose scenes were planned
 * again (render them to apply the change).
 */
export interface ZoomOutResult {
  project: Project;
  clip_ids: number[];
}
/**
 * What the server keeps of a campaign besides the owner's entries; it
 * comes first in Campaign's fields.
 */
export interface _CampaignSaved {
  id: number;
  permission_screenshot_asset_id: number | null;
  permission_checked_at: string | null;
}
