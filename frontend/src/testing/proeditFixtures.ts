import type {
  EdlItem,
  ProEditChoices,
  ProEditEstimate,
  ProEditOptions,
  ProEditPlan,
  ProEditRun,
  ProEditTiming,
} from "@/api/types";

const PRESETS: ProEditChoices["presets"] = [
  ["clean_pro", "Clean Pro"],
  ["dark_edit", "Dark Edit"],
  ["phonk_edit", "Phonk Edit"],
  ["cinematic", "Cinematic"],
  ["skull_moment", "Skull Moment"],
  ["glitch", "Glitch"],
].map(([id, name]) => ({
  id: id as ProEditOptions["preset"],
  name,
  description: `${name} look.`,
  music_moods: ["dark"],
  bpm_min: 90,
  bpm_max: 140,
}));

/** What the dialog offers: the six presets, a loop and an upload, a
 * recipe; no campaign. */
export const CHOICES: ProEditChoices = {
  presets: PRESETS,
  music: [
    { id: "night_drive", title: "Night Drive", tags: ["dark"], bundled: true },
    { id: "42", title: "My Song.wav", tags: [], bundled: false },
  ],
  recipes: [
    {
      id: 3,
      name: "Night phonk",
      description: "Fast cuts",
      features: {},
      reference_count: 2,
      created_at: "2026-11-07T10:00:00",
    },
  ],
  campaign_id: null,
  campaign_name: null,
  allow_heavy_edits: null,
  max_intensity: "extreme",
};

/** A cost estimate of a run with the critic. */
export function estimate(
  overrides: Partial<ProEditEstimate> = {},
): ProEditEstimate {
  return {
    director_tokens: 4000,
    director_usd: 0.01,
    critic_tokens: 9000,
    critic_usd: 0.03,
    critic_rounds: 2,
    text: "About $0.04 with the critic (2 rounds).",
    monthly_cap_usd: null,
    month_spend_usd: 0,
    blocked: false,
    ...overrides,
  };
}

/** A queued start run of variant 12 with options (job 77). */
export function proEditRun(options: ProEditOptions | null = null): ProEditRun {
  return {
    id: 5,
    clip_id: 12,
    plan_id: null,
    status: "queued",
    rounds: 0,
    critic_scores: [],
    cost_estimate: null,
    cost_actual: null,
    started_at: null,
    finished_at: null,
    error: null,
    job_id: 77,
    mode: "start",
    options,
    notes: [],
  };
}

/** An auto item of a plan. */
export function edlItem(
  id: number,
  kind: EdlItem["kind"],
  t_start: number,
  t_end: number,
  reason = `${kind} reason`,
): EdlItem {
  return { id, kind, t_start, t_end, params: {}, reason, source: "auto" };
}

/** Plan 40 v1 of variant 12: a zoom punch at 2-2.5 s and a whoosh at 5 s. */
export const PLAN: ProEditPlan = {
  id: 40,
  clip_id: 12,
  preset: "phonk_edit",
  intensity: "pro",
  style_recipe_id: null,
  version: 1,
  items: [
    edlItem(1, "zoom_punch", 2, 2.5, "punch on the hook"),
    edlItem(2, "sfx", 5, 5.5, "whoosh into the reveal"),
  ],
  rationale: "Phonk Edit.",
  created_by: "rule_director",
};

/** Variant 12 is 10 s at 30 fps, with two words and a beat every 0.5 s. */
export const TIMING: ProEditTiming = {
  fps: 30,
  duration: 10,
  words: [
    { text: "why", start: 1.1, end: 1.4 },
    { text: "now", start: 4.02, end: 4.3 },
  ],
  beats: [0.5, 1, 1.5, 2, 2.5, 3],
};

/** Plan 41 v2 of variant 12: the critic moved the zoom punch, dropped the
 * whoosh and added a flash. */
export const PLAN_V2: ProEditPlan = {
  ...PLAN,
  id: 41,
  version: 2,
  created_by: "critic_revision",
  items: [
    {
      ...edlItem(1, "zoom_punch", 2.2, 2.7, "punch on the hook"),
      params: { scale: 1.3, ease: "ease_in_out", ease_frames: 0 },
    },
    edlItem(3, "flash", 3, 3.1, "flash on the beat"),
  ],
};

/** A done critic run of variant 12 with two rounds: the first revised the
 * plan, the second passed. */
export function criticRun(): ProEditRun {
  return {
    ...proEditRun(),
    status: "done",
    plan_id: 41,
    rounds: 2,
    critic_scores: [
      {
        round: 1,
        plan_version: 1,
        scores: [
          { check: "Hook strength", score: 4, reason: "The hook is flat." },
          { check: "Dead air", score: 9, reason: "No gaps." },
        ],
        changes: [
          {
            op: "modify",
            item_id: 1,
            before: PLAN.items[0],
            after: PLAN_V2.items[0],
            reason: "Land the punch on the word.",
          },
        ],
        ignored: [
          {
            op: "remove",
            item_id: 9,
            kind: null,
            reason: "Not needed.",
            problem: "item 9 does not exist",
          },
        ],
        notes: [],
      },
      {
        round: 2,
        plan_version: 2,
        scores: [
          { check: "Hook strength", score: 8, reason: "Strong now." },
          { check: "Dead air", score: 9, reason: "No gaps." },
        ],
        changes: [],
        ignored: [],
        notes: ["Every score passed."],
      },
    ],
  };
}
