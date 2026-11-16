import type { ProEditOptions } from "@/api/types";

export type Intensity = ProEditOptions["intensity"];
export type PresetId = ProEditOptions["preset"];
export type Background = ProEditOptions["background"];

/** The intensities from the lightest to the heaviest (SPEC-v3 1.3). */
export const INTENSITIES: readonly Intensity[] = [
  "clean",
  "standard",
  "pro",
  "extreme",
];

export const INTENSITY_LABEL: Record<Intensity, string> = {
  clean: "Clean",
  standard: "Standard",
  pro: "Pro",
  extreme: "Extreme",
};

/** The presets in the order of the dialog, with their names. */
export const PRESET_LABEL: Record<PresetId, string> = {
  clean_pro: "Clean Pro",
  dark_edit: "Dark Edit",
  phonk_edit: "Phonk Edit",
  cinematic: "Cinematic",
  skull_moment: "Skull Moment",
  glitch: "Glitch",
};

/** The backgrounds of the subject cut-out, in the order of the dialog. */
export const BACKGROUNDS: readonly Background[] = ["keep", "blur", "swap"];

export const BACKGROUND_LABEL: Record<Background, string> = {
  keep: "Keep",
  blur: "Blur",
  swap: "Swap for a color",
};

/** The music choice that lets the Director pick a bed by mood and BPM. */
export const AUTO_MUSIC = "auto";
/** The music choice of no bed. */
export const NO_MUSIC = "none";

/** The options the dialog opens with: ProEditOptions' server defaults. */
export const DEFAULT_OPTIONS: ProEditOptions = {
  preset: "clean_pro",
  intensity: "standard",
  style_recipe_id: null,
  music: AUTO_MUSIC,
  use_critic: true,
  loop_ending: false,
  subject_front: false,
  background: "keep",
  background_color: "#101014",
};

/** The intensities up to and including max (the campaign's cap). */
export function intensitiesUpTo(max: Intensity): Intensity[] {
  return INTENSITIES.slice(0, INTENSITIES.indexOf(max) + 1);
}

/** The query string of GET /proedit/clips/{id}/estimate for options. */
export function estimateQuery(options: ProEditOptions): string {
  const params = new URLSearchParams({
    preset: options.preset,
    intensity: options.intensity,
    music: options.music,
    use_critic: String(options.use_critic),
    loop_ending: String(options.loop_ending),
  });
  if (options.style_recipe_id !== null) {
    params.set("style_recipe_id", String(options.style_recipe_id));
  }
  return params.toString();
}
