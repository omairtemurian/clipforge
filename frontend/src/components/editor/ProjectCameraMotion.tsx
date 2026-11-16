import { useQueryClient } from "@tanstack/react-query";
import { clipQuery } from "@/api/clips";
import { useSetCameraMotion } from "@/api/projects";
import type { Project } from "@/api/types";
import {
  CameraMotionField,
  type CameraMotion,
} from "@/components/settings/CameraMotionField";
import type { ClipEdits } from "@/hooks/useClipEdits";
import { toast } from "@/lib/toast";

/**
 * The reframe panel's camera motion control: how the project's
 * auto-tracking windows move, saved at once and applied to the crop plans
 * of the project's clips (PUT /projects/{id}/camera-motion). The clip
 * being edited is fetched again; its rendered video changes once it is
 * rendered again.
 */
export function ProjectCameraMotion({
  clipId,
  project,
  edits,
}: {
  clipId: number;
  project: Project;
  edits: ClipEdits;
}) {
  const queryClient = useQueryClient();
  const setMotion = useSetCameraMotion(project.id);

  async function change(motion: CameraMotion) {
    const result = await setMotion.mutateAsync(motion);
    const clip = await queryClient.fetchQuery({
      ...clipQuery(clipId),
      staleTime: 0,
    });
    edits.reset(clip);
    const count = result.clip_ids.length;
    toast.success(
      count === 0
        ? "Camera motion saved. No clip needed tracking again."
        : `Camera motion saved. ${count} ${count === 1 ? "clip" : "clips"} re-tracked. Render them to apply.`,
    );
  }

  return (
    <div className="flex flex-col gap-1.5">
      <CameraMotionField
        value={project.settings.camera_motion}
        onChange={(value) => void change(value)}
        disabled={edits.dirty || setMotion.isPending}
      />
      <p className="text-caption text-muted-foreground">
        {edits.dirty
          ? "Save this clip before you change how every clip is tracked"
          : "For every clip of this project."}
      </p>
    </div>
  );
}
