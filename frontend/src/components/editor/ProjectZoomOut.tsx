import { useQueryClient } from "@tanstack/react-query";
import { clipQuery } from "@/api/clips";
import { useSetZoomOut } from "@/api/projects";
import type { Project } from "@/api/types";
import {
  ZoomOutMoments,
  type ZoomOutIntensity,
} from "@/components/settings/ZoomOutMoments";
import { ZOOMS_OUT } from "@/lib/processingSettings";
import type { ClipEdits } from "@/hooks/useClipEdits";
import { toast } from "@/lib/toast";

/** Why the control is unavailable, if it is. */
function blocked(project: Project, dirty: boolean): string | undefined {
  if (!ZOOMS_OUT.includes(project.settings.default_layout)) {
    return "Needs the Automatic or Switch per segment default layout";
  }
  return dirty ? "Save this clip first: it plans every clip again" : undefined;
}

/**
 * The reframe panel's zoom-out moments control: the project's intensity,
 * saved at once and applied to the project's clips that have no manual
 * scenes (PUT /projects/{id}/zoom-out). The clip being edited then shows
 * its new scenes; its rendered video changes once it is rendered again.
 */
export function ProjectZoomOut({
  clipId,
  project,
  edits,
}: {
  clipId: number;
  project: Project;
  edits: ClipEdits;
}) {
  const queryClient = useQueryClient();
  const setZoomOut = useSetZoomOut(project.id);
  const reason = blocked(project, edits.dirty);

  async function change(intensity: ZoomOutIntensity) {
    const result = await setZoomOut.mutateAsync(intensity);
    const clip = await queryClient.fetchQuery({
      ...clipQuery(clipId),
      staleTime: 0,
    });
    edits.reset(clip);
    const count = result.clip_ids.length;
    toast.success(
      count === 0
        ? "Zoom-out moments saved. No clip needed planning again."
        : `Zoom-outs planned again for ${count} ${count === 1 ? "clip" : "clips"}. Render them to apply.`,
    );
  }

  return (
    <div className="flex flex-col gap-1.5">
      <ZoomOutMoments
        value={project.settings.zoom_out_moments}
        onChange={(value) => void change(value)}
        disabled={reason !== undefined || setZoomOut.isPending}
        hint={reason}
      />
      <p className="text-caption text-muted-foreground">
        For every clip of this project that has no scenes of your own.
      </p>
    </div>
  );
}
