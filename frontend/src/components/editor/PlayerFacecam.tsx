import { ArrowCounterClockwiseIcon } from "@phosphor-icons/react";
import { useRef } from "react";
import type { Clip, CropTrack } from "@/api/types";
import { CropBoxEditor } from "@/components/CropBoxEditor";
import { CropTrackGate, SourceFrame } from "@/components/editor/SourceFrame";
import { Button } from "@/components/ui/button";
import type { ClipEdits } from "@/hooks/useClipEdits";
import {
  facecamRect,
  MIN_FACECAM,
  rectToBox,
  type FacecamSource,
} from "@/lib/facecam";

const NOTES: Record<FacecamSource, string> = {
  drawn: "Your facecam box, used in every facecam scene of the clip.",
  found: "The facecam box found around the speaker's face. Drag to change it.",
  none: "No face was found: drag the box over the facecam to show it.",
};

interface PlayerFacecamProps {
  clip: Clip;
  edits: ClipEdits;
  /** The playhead's source time in seconds. */
  time: number;
}

/**
 * The crop tool of a screenshare or gameplay scene: the source frame at
 * the playhead with the facecam box over it (lib/facecam). Dragging or
 * resizing it (in any shape) sets the clip's facecam box (its framing's);
 * "Use the found box" ("Remove the box" if none was found) drops it.
 */
export function PlayerFacecam({ clip, edits, time }: PlayerFacecamProps) {
  return (
    <CropTrackGate clip={clip} edits={edits}>
      {(track) => (
        <FacecamFrame clip={clip} edits={edits} time={time} track={track} />
      )}
    </CropTrackGate>
  );
}

/** The facecam tool once the clip's crop track is loaded. */
function FacecamFrame({
  clip,
  edits,
  time,
  track,
}: PlayerFacecamProps & { track: CropTrack }) {
  const frameRef = useRef<HTMLDivElement>(null);
  const { framing } = edits.look;
  const frame = { width: track.frame_width, height: track.frame_height };
  const { rect, source } = facecamRect(framing, track);

  return (
    <div className="flex size-full flex-col items-center justify-center gap-3">
      <SourceFrame
        projectId={clip.project_id}
        time={time}
        frame={frame}
        frameRef={frameRef}
      >
        <CropBoxEditor
          frame={frame}
          rect={rect}
          resize={{ shape: "free", minSize: frame.height * MIN_FACECAM }}
          label="Facecam box"
          onChange={(next, gesture) =>
            edits.setLook(
              { framing: { ...framing, facecam: rectToBox(next, frame) } },
              gesture,
            )
          }
        >
          <span className="absolute top-1 left-1 rounded bg-primary px-1.5 py-0.5 text-[10px] font-medium text-primary-foreground">
            Facecam
          </span>
        </CropBoxEditor>
      </SourceFrame>
      <div className="flex items-center gap-2 text-caption text-muted-foreground">
        <span aria-live="polite">{NOTES[source]}</span>
        <Button
          type="button"
          variant="ghost"
          size="xs"
          disabled={source !== "drawn"}
          onClick={() =>
            edits.setLook({ framing: { ...framing, facecam: null } })
          }
        >
          <ArrowCounterClockwiseIcon aria-hidden />
          {track.facecam ? "Use the found box" : "Remove the box"}
        </Button>
      </div>
    </div>
  );
}
