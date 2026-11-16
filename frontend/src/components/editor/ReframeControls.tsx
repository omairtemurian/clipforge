import { useState, type FormEvent } from "react";
import type { Aspect } from "@/api/clips";
import { useReframePresets } from "@/api/reframe";
import type { Project } from "@/api/types";
import { ProjectCameraMotion } from "@/components/editor/ProjectCameraMotion";
import { ProjectZoomOut } from "@/components/editor/ProjectZoomOut";
import { INPUT } from "@/components/settings/Field";
import { Button } from "@/components/ui/button";
import type { ClipEdits } from "@/hooks/useClipEdits";
import { parseRatio } from "@/lib/aspectRatio";
import { cn } from "@/lib/utils";

interface ReframeControlsProps {
  clipId: number;
  edits: ClipEdits;
  project: Project | undefined;
  /** Whether the scene at the playhead is a track scene. */
  tracking: boolean;
}

/**
 * The reframe part of the editor's Layout tab: a custom output ratio for
 * the clip ("W:H", from 1:4 to 4:1; the toolbar lists the common ones),
 * the project's reframe style (chosen in the settings, it shaped the
 * clip's first framing), the project's camera motion and zoom-out
 * moments and how to point the tracker at a subject.
 */
export function ReframeControls({
  clipId,
  edits,
  project,
  tracking,
}: ReframeControlsProps) {
  const [text, setText] = useState("");
  const [invalid, setInvalid] = useState(false);
  const presets = useReframePresets().data;
  const projectAspect: Aspect = project?.settings.aspect ?? "9:16";
  const aspect = edits.look.framing.aspect ?? projectAspect;
  const name = project?.settings.reframe_preset ?? null;
  const style = presets?.find((preset) => preset.name === name);

  function submit(event: FormEvent) {
    event.preventDefault();
    const next = parseRatio(text);
    setInvalid(next === null);
    if (next === null) return;
    edits.setLook({
      framing: {
        ...edits.look.framing,
        aspect: next === projectAspect ? null : next,
      },
    });
    setText("");
  }

  return (
    <section aria-label="Reframe" className="flex flex-col gap-3">
      <form onSubmit={submit} className="flex flex-col gap-1.5">
        <label htmlFor="custom-ratio" className="text-body font-medium">
          Custom ratio
        </label>
        <div className="flex gap-2">
          <input
            id="custom-ratio"
            value={text}
            placeholder="e.g. 3:4"
            aria-invalid={invalid}
            aria-describedby="custom-ratio-help"
            onChange={(event) => {
              setText(event.target.value);
              setInvalid(false);
            }}
            className={cn(INPUT, "h-9", invalid && "border-destructive")}
          />
          <Button type="submit" variant="outline" disabled={!text.trim()}>
            Set
          </Button>
        </div>
        <p
          id="custom-ratio-help"
          role={invalid ? "alert" : undefined}
          className={cn(
            "text-caption",
            invalid ? "text-destructive" : "text-muted-foreground",
          )}
        >
          {invalid
            ? "Use W:H, such as 3:4, no wider or taller than 4:1."
            : `The clip is ${aspect} now. Shows after you save.`}
        </p>
      </form>
      <p className="text-caption text-muted-foreground">
        Reframe style: {style?.label ?? "Automatic"}
        {style ? `. ${style.description}` : ""}
      </p>
      {project && (
        <>
          <ProjectCameraMotion
            clipId={clipId}
            project={project}
            edits={edits}
          />
          <ProjectZoomOut clipId={clipId} project={project} edits={edits} />
        </>
      )}
      <p className="text-caption text-muted-foreground">
        {tracking
          ? "Click the subject in the picker to track it, or drag a box around it."
          : "To follow one subject, switch the scene to Track and click it."}
      </p>
    </section>
  );
}
