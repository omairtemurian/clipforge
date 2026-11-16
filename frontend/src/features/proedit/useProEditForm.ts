import { useState } from "react";
import type { ProEditChoices, ProEditOptions } from "@/api/types";
import {
  DEFAULT_OPTIONS,
  INTENSITIES,
  intensitiesUpTo,
  type Intensity,
} from "./options";

/** The warning the dialog shows for the campaign's heavy-edit rule, or
 * null: none without a campaign or when the campaign allows heavy edits. */
export function heavyEditsWarning(
  choices: Pick<
    ProEditChoices,
    "campaign_id" | "campaign_name" | "allow_heavy_edits"
  >,
): string | null {
  if (choices.campaign_id === null || choices.allow_heavy_edits === "true") {
    return null;
  }
  const name = choices.campaign_name ?? "This clip's campaign";
  return choices.allow_heavy_edits === "false"
    ? `${name} does not allow heavy edits. A Pro Edit variant may break its rules; post the original instead.`
    : `${name} does not say whether heavy edits are allowed. Check its rules before posting a Pro Edit variant.`;
}

/** The lighter of intensity and max. */
function capped(intensity: Intensity, max: Intensity): Intensity {
  return INTENSITIES.indexOf(intensity) > INTENSITIES.indexOf(max)
    ? max
    : intensity;
}

export interface ProEditForm {
  options: ProEditOptions;
  /** The intensities the slider reaches (up to the campaign's cap). */
  intensities: Intensity[];
  setPreset: (preset: ProEditOptions["preset"]) => void;
  setIntensity: (intensity: Intensity) => void;
  setRecipe: (recipeId: number | null) => void;
  setMusic: (music: string) => void;
  setUseCritic: (useCritic: boolean) => void;
  setLoopEnding: (loopEnding: boolean) => void;
  setSubjectFront: (subjectFront: boolean) => void;
  setBackground: (background: ProEditOptions["background"]) => void;
  setBackgroundColor: (color: string) => void;
}

/**
 * The state of the Pro Edit dialog's form: ProEditOptions starting at the
 * defaults, with the intensity kept within the campaign's cap
 * (choices.max_intensity).
 */
export function useProEditForm(
  choices: Pick<ProEditChoices, "max_intensity">,
): ProEditForm {
  const max = choices.max_intensity;
  const [options, setOptions] = useState<ProEditOptions>(DEFAULT_OPTIONS);
  const update = (change: Partial<ProEditOptions>) =>
    setOptions((previous) => ({ ...previous, ...change }));

  return {
    options: { ...options, intensity: capped(options.intensity, max) },
    intensities: intensitiesUpTo(max),
    setPreset: (preset) => update({ preset }),
    setIntensity: (intensity) => update({ intensity: capped(intensity, max) }),
    setRecipe: (style_recipe_id) => update({ style_recipe_id }),
    setMusic: (music) => update({ music }),
    setUseCritic: (use_critic) => update({ use_critic }),
    setLoopEnding: (loop_ending) => update({ loop_ending }),
    setSubjectFront: (subject_front) => update({ subject_front }),
    setBackground: (background) => update({ background }),
    setBackgroundColor: (background_color) => update({ background_color }),
  };
}
