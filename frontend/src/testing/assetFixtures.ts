import type { Asset } from "@/api/types";

/** The audio fields of an Asset that was not analyzed (or is not audio). */
export const NO_AUDIO_DATA = {
  bpm: null,
  key: null,
  loudness_lufs: null,
  energy_curve: null,
  category: null,
  mood: null,
  downloaded_at: null,
} satisfies Pick<
  Asset,
  | "bpm"
  | "key"
  | "loudness_lufs"
  | "energy_curve"
  | "category"
  | "mood"
  | "downloaded_at"
>;
