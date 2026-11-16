import { WarningIcon } from "@phosphor-icons/react";
import { Link } from "react-router-dom";
import type { ProEditChoices, ProEditEstimate } from "@/api/types";
import { NativeSelect } from "@/components/ui/native-select";
import { ToggleRow } from "@/components/ui/toggle-row";
import { cn } from "@/lib/utils";
import { AUTO_MUSIC, INTENSITY_LABEL, NO_MUSIC } from "./options";
import { styleRecipesPath } from "./paths";
import type { ProEditForm } from "./useProEditForm";

const FIELD = "flex flex-col gap-1.5";
const LABEL = "text-body font-medium";

/** The intensity slider, from Clean to the campaign's cap. */
export function IntensityField({
  form,
  capped,
}: {
  form: ProEditForm;
  capped: boolean;
}) {
  const index = form.intensities.indexOf(form.options.intensity);
  return (
    <div className={FIELD}>
      <label htmlFor="proedit-intensity" className={LABEL}>
        Intensity
        <span className="ml-2 text-caption font-normal text-muted-foreground">
          {INTENSITY_LABEL[form.options.intensity]}
        </span>
      </label>
      <input
        id="proedit-intensity"
        type="range"
        min={0}
        max={form.intensities.length - 1}
        step={1}
        value={index}
        aria-valuetext={INTENSITY_LABEL[form.options.intensity]}
        onChange={(event) =>
          form.setIntensity(form.intensities[Number(event.target.value)])
        }
        className="w-full accent-primary"
      />
      <div className="flex justify-between text-caption text-muted-foreground">
        {form.intensities.map((intensity) => (
          <span key={intensity}>{INTENSITY_LABEL[intensity]}</span>
        ))}
      </div>
      {capped && (
        <p className="text-caption text-muted-foreground">
          The campaign's autopilot caps Pro Edit at{" "}
          {INTENSITY_LABEL[form.intensities[form.intensities.length - 1]]}.
        </p>
      )}
    </div>
  );
}

/** The optional style recipe (with a link to the recipes page) and the
 * music bed. */
export function RecipeAndMusicFields({
  form,
  choices,
}: {
  form: ProEditForm;
  choices: ProEditChoices;
}) {
  const bundled = choices.music.filter((track) => track.bundled);
  const uploads = choices.music.filter((track) => !track.bundled);
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      <div className={FIELD}>
        <label htmlFor="proedit-recipe" className={LABEL}>
          Style recipe
        </label>
        <NativeSelect
          id="proedit-recipe"
          block
          value={form.options.style_recipe_id ?? ""}
          onChange={(event) =>
            form.setRecipe(
              event.target.value === "" ? null : Number(event.target.value),
            )
          }
        >
          <option value="">None (preset only)</option>
          {choices.recipes.map((recipe) => (
            <option key={recipe.id} value={recipe.id}>
              {recipe.name}
            </option>
          ))}
        </NativeSelect>
        <Link
          to={styleRecipesPath(form.options.style_recipe_id ?? undefined)}
          className="text-caption text-primary-ink underline-offset-4 hover:underline"
        >
          Manage style recipes
        </Link>
      </div>
      <div className={FIELD}>
        <label htmlFor="proedit-music" className={LABEL}>
          Music
        </label>
        <NativeSelect
          id="proedit-music"
          block
          value={form.options.music}
          onChange={(event) => form.setMusic(event.target.value)}
        >
          <option value={AUTO_MUSIC}>Auto (by mood and BPM)</option>
          <option value={NO_MUSIC}>No music</option>
          {bundled.length > 0 && (
            <optgroup label="Bundled loops">
              {bundled.map((track) => (
                <option key={track.id} value={track.id}>
                  {track.title}
                </option>
              ))}
            </optgroup>
          )}
          {uploads.length > 0 && (
            <optgroup label="Your music">
              {uploads.map((track) => (
                <option key={track.id} value={track.id}>
                  {track.title}
                </option>
              ))}
            </optgroup>
          )}
        </NativeSelect>
      </div>
    </div>
  );
}

/** The cost line under the critic toggle: the estimate, why it is blocked
 * (the monthly cap), or why there is none. */
function estimateText(
  estimate: ProEditEstimate | undefined,
  error: Error | null,
): string {
  if (estimate?.blocked) {
    return `${estimate.text} The monthly LLM cap is used up.`;
  }
  if (estimate) return estimate.text;
  if (error) return `No cost estimate: ${error.message}`;
  return "Estimating the cost…";
}

/** The "Use critic" toggle with the run's LLM cost estimate. */
export function CriticField({
  form,
  estimate,
  error,
}: {
  form: ProEditForm;
  estimate: ProEditEstimate | undefined;
  error: Error | null;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <ToggleRow
        label="Use critic"
        hint="A vision model watches proxies and fixes the plan before the final render."
        checked={form.options.use_critic}
        onCheckedChange={form.setUseCritic}
      />
      <p
        aria-live="polite"
        aria-label="Cost estimate"
        className={cn(
          "text-caption",
          estimate?.blocked ? "text-destructive" : "text-muted-foreground",
        )}
      >
        {estimateText(estimate, error)}
      </p>
    </div>
  );
}

/** The "Loop-friendly ending" toggle (SPEC-v3 3.3 retention). */
export function LoopField({ form }: { form: ProEditForm }) {
  return (
    <ToggleRow
      label="Loop-friendly ending"
      hint="The last 0.3 s blend back into the first frame and sound, so the clip replays seamlessly."
      checked={form.options.loop_ending}
      onCheckedChange={form.setLoopEnding}
    />
  );
}

/** The warning about the campaign's heavy-edit rule. */
export function HeavyEditsWarning({ text }: { text: string }) {
  return (
    <p
      role="alert"
      className="flex items-start gap-2 rounded-xl border border-warning/40 bg-warning/10 p-3 text-body text-warning"
    >
      <WarningIcon className="mt-0.5 size-4 shrink-0" aria-hidden />
      {text}
    </p>
  );
}
