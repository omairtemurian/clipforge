import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useQueueRender, useSaveClip, useSaveTracks } from "@/api/clipActions";
import { projectsKey } from "@/api/projects";
import type { Clip } from "@/api/types";
import type { ClipEdits } from "@/hooks/useClipEdits";
import { useJobEvents } from "@/hooks/useJobEvents";
import { toast } from "@/lib/toast";

export interface ClipExport {
  /** Save the edits (PATCH the clip, then its layer tracks if they
   * changed); true if they are saved. */
  save: () => Promise<boolean>;
  saving: boolean;
  /** Save any unsaved edits, then render the clip with a render job. */
  render: () => Promise<void>;
  /** A render job is queued or running for the clip. */
  rendering: boolean;
  /** The running job's progress from 0 to 1, once it reports any. */
  progress: number | null;
  /** The rendered video is there to download. */
  downloadable: boolean;
}

/**
 * Saving, rendering and downloading the edited clip. The render job's
 * progress follows its server-sent events; its end reloads the clip and
 * tells the user. A render the page did not start (the clip is
 * "rendering") is followed by the clip's own refresh.
 */
export function useClipExport(clip: Clip, edits: ClipEdits): ClipExport {
  const queryClient = useQueryClient();
  const saveClip = useSaveClip(clip.id);
  const saveTracks = useSaveTracks(clip.id);
  const queue = useQueueRender(clip.id);
  const [jobId, setJobId] = useState<number>();

  const events = useJobEvents(jobId, (event) => {
    setJobId(undefined);
    void queryClient.invalidateQueries({ queryKey: ["clips", clip.id] });
    void queryClient.invalidateQueries({
      queryKey: [...projectsKey, clip.project_id, "clips"],
    });
    if (event.status === "done") {
      toast.success("The clip is rendered. Download it now.");
    } else {
      toast.error(`Rendering failed: ${event.message}`);
    }
  });

  const save = async () => {
    try {
      await saveClip.mutateAsync(edits.patch);
      if (edits.layersDirty) await saveTracks.mutateAsync(edits.layers);
      return true;
    } catch {
      return false; // apiFetch has shown the error
    }
  };

  const render = async () => {
    if (edits.dirty && !(await save())) return;
    try {
      const job = await queue.mutateAsync();
      setJobId(job.id);
      toast.info("Rendering the clip. This takes a minute.");
    } catch {
      // apiFetch has shown the error
    }
  };

  const rendering =
    jobId !== undefined || queue.isPending || clip.status === "rendering";
  return {
    save,
    saving: saveClip.isPending || saveTracks.isPending,
    render,
    rendering,
    progress: events.event?.progress ?? null,
    downloadable: clip.status === "rendered" && !rendering,
  };
}
