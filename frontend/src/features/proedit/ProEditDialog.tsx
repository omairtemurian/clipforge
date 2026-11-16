import { CircleNotchIcon, MagicWandIcon } from "@phosphor-icons/react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { apiUrl } from "@/api/client";
import { useProject } from "@/api/projects";
import type { Clip, ProEditChoices, ProEditStarted } from "@/api/types";
import { Button } from "@/components/ui/button";
import { DialogFrame } from "@/components/ui/dialog-frame";
import { Skeleton } from "@/components/ui/skeleton";
import { CutoutField } from "./CutoutField";
import { PresetCard } from "./PresetCard";
import {
  CriticField,
  LoopField,
  HeavyEditsWarning,
  IntensityField,
  RecipeAndMusicFields,
} from "./ProEditFields";
import { ProEditProgress } from "./ProEditProgress";
import { proEditPath } from "./paths";
import {
  useProEditChoices,
  useProEditEstimate,
  useStartProEdit,
} from "./runApi";
import { heavyEditsWarning, useProEditForm } from "./useProEditForm";

interface FormProps {
  clip: Clip;
  choices: ProEditChoices;
  posterUrl: string | null;
  onStarted: (started: ProEditStarted) => void;
  onClose: () => void;
}

/** The options of a new Pro Edit variant, scrolling inside the dialog, and
 * a footer with Cancel and Run that stays in view. */
function ProEditForm({
  clip,
  choices,
  posterUrl,
  onStarted,
  onClose,
}: FormProps) {
  const form = useProEditForm(choices);
  const estimate = useProEditEstimate(clip.id, form.options);
  const start = useStartProEdit(clip.id);
  const warning = heavyEditsWarning(choices);
  const blocked = estimate.data?.blocked === true;

  return (
    <form
      className="mt-5 flex min-h-0 flex-col gap-4"
      onSubmit={(event) => {
        event.preventDefault();
        start.mutate(form.options, { onSuccess: onStarted });
      }}
    >
      <div
        role="group"
        aria-label="Pro Edit options"
        className="-mx-1 flex min-h-0 flex-col gap-5 overflow-y-auto px-1 pb-1"
      >
        {warning && <HeavyEditsWarning text={warning} />}
        <fieldset className="flex flex-col gap-2">
          <legend className="mb-2 text-body font-medium">Preset</legend>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            {choices.presets.map((preset) => (
              <PresetCard
                key={preset.id}
                preset={preset}
                posterUrl={posterUrl}
                checked={form.options.preset === preset.id}
                onPick={form.setPreset}
              />
            ))}
          </div>
        </fieldset>
        <IntensityField
          form={form}
          capped={choices.max_intensity !== "extreme"}
        />
        <RecipeAndMusicFields form={form} choices={choices} />
        <LoopField form={form} />
        <CutoutField form={form} />
        <CriticField
          form={form}
          estimate={estimate.data}
          error={estimate.error}
        />
      </div>
      <div className="flex shrink-0 flex-wrap items-center justify-between gap-3 border-t border-border pt-4">
        <Link
          to={proEditPath(clip.id)}
          className="text-body text-primary-ink underline-offset-4 hover:underline"
        >
          See this clip's Pro Edit variants
        </Link>
        <div className="flex gap-2">
          <Button type="button" variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button
            type="submit"
            disabled={start.isPending || blocked}
            title={blocked ? "The monthly LLM cap is used up" : undefined}
          >
            {start.isPending ? (
              <CircleNotchIcon className="animate-spin" aria-hidden />
            ) : (
              <MagicWandIcon aria-hidden />
            )}
            Run Pro Edit
          </Button>
        </div>
      </div>
    </form>
  );
}

/** The project's thumbnail URL, or null while unknown or without one. */
function usePosterUrl(projectId: number): string | null {
  const project = useProject(projectId);
  return project.data?.thumbnail_path
    ? apiUrl(`/media/${projectId}/thumbnail`)
    : null;
}

/**
 * The Pro Edit dialog of an original clip (SPEC-v3 3.8): preset cards with
 * a looping preview, the intensity slider (up to the campaign's cap), an
 * optional style recipe, the music, a loop-friendly ending, the subject
 * cut-out, "Use critic" with the cost estimate, and a warning when the campaign does not allow heavy edits. Run queues a
 * variant and the dialog follows its progress.
 */
export function ProEditDialog({
  clip,
  onClose,
}: {
  clip: Clip;
  onClose: () => void;
}) {
  const choices = useProEditChoices(clip.id);
  const posterUrl = usePosterUrl(clip.project_id);
  const [started, setStarted] = useState<ProEditStarted | null>(null);

  let body;
  if (started) {
    body = <ProEditProgress started={started} originalId={clip.id} />;
  } else if (choices.isPending) {
    body = (
      <div className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-3">
        {Array.from({ length: 6 }, (_, index) => (
          <Skeleton key={index} className="aspect-[5/4] rounded-xl" />
        ))}
      </div>
    );
  } else if (choices.isError) {
    body = (
      <p role="alert" className="mt-5 text-body text-destructive">
        Could not load the Pro Edit options: {choices.error.message}
      </p>
    );
  } else {
    body = (
      <ProEditForm
        clip={clip}
        choices={choices.data}
        posterUrl={posterUrl}
        onStarted={setStarted}
        onClose={onClose}
      />
    );
  }

  return (
    <DialogFrame
      wide
      title={started ? "Pro Edit running" : "Pro Edit"}
      description={
        started
          ? `Making a Pro Edit variant of “${clip.title}”. You can close this; the job keeps running.`
          : `Make a heavy-edit variant of “${clip.title}”. The original clip stays as it is.`
      }
      onClose={onClose}
    >
      {body}
    </DialogFrame>
  );
}
