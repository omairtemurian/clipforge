import type {
  StyleMatch,
  StyleMetric,
  StyleRecipe,
  StyleRecipeDetail,
} from "@/api/types";

/** Three metrics of the server's list: cuts, brightness and tempo. */
export const METRICS: StyleMetric[] = [
  {
    key: "cuts_per_minute",
    label: "Cuts",
    unit: "/min",
    group: "rhythm",
    min: 0,
    max: 120,
    step: 1,
    tolerance: 6,
  },
  {
    key: "mean_luma",
    label: "Brightness",
    unit: "share",
    group: "look",
    min: 0,
    max: 1,
    step: 0.01,
    tolerance: 0.05,
  },
  {
    key: "bpm",
    label: "Music tempo",
    unit: "BPM",
    group: "audio",
    min: 40,
    max: 220,
    step: 1,
    tolerance: 8,
  },
];

/** Recipe 3, made from two reference links. */
export const RECIPE: StyleRecipe = {
  id: 3,
  name: "Night phonk",
  description: "Fast cuts on the beat.",
  features: {},
  reference_count: 2,
  created_at: "2026-11-07T10:00:00",
};

/** Recipe 3 analyzed: cuts and brightness measured, no tempo target. */
export const DETAIL: StyleRecipeDetail = {
  recipe: RECIPE,
  references: [1, 2].map((id) => ({
    reference: {
      id,
      recipe_id: 3,
      url: `https://www.youtube.com/shorts/ref${id}`,
      analyzed_at: "2026-11-07T10:05:00",
      deleted_at: "2026-11-07T10:05:01",
      rights_confirmed_at: "2026-11-07T10:00:00",
    },
    error: null,
  })),
  targets: {
    metrics: {
      cuts_per_minute: { median: 30, low: 18, high: 42, count: 2 },
      mean_luma: { median: 0.3, low: 0.24, high: 0.36, count: 2 },
    },
    caption_color: "#ffd000",
  },
};

/** Variant 12 measured against recipe 3: cuts fit, brightness does not. */
export const MATCH: StyleMatch = {
  clip_id: 12,
  recipe_id: 3,
  recipe_name: "Night phonk",
  score: 75,
  metrics: [
    {
      key: "cuts_per_minute",
      label: "Cuts",
      unit: "/min",
      value: 31,
      target: { median: 30, low: 18, high: 42, count: 2 },
      score: 1,
    },
    {
      key: "mean_luma",
      label: "Brightness",
      unit: "share",
      value: 0.6,
      target: { median: 0.3, low: 0.24, high: 0.36, count: 2 },
      score: 0.5,
    },
  ],
  measured_at: "2026-11-07T11:00:00",
};
