import { CaretLeftIcon, CaretRightIcon } from "@phosphor-icons/react";
import { AutoCutToggle } from "@/components/editor/AutoCutToggle";
import { AutoZoomToggle } from "@/components/editor/AutoZoomToggle";
import { PanelSlider } from "@/components/editor/PanelSlider";
import { ReframeControls } from "@/components/editor/ReframeControls";
import { SceneChooser } from "@/components/editor/SceneChooser";
import type { Project } from "@/api/types";
import { Button } from "@/components/ui/button";
import { PanelGroup } from "@/components/ui/panel";
import type { ClipEdits } from "@/hooks/useClipEdits";
import { useGesture } from "@/hooks/useGesture";
import type { SceneEdits } from "@/hooks/useSceneEdits";
import type { SceneTracker } from "@/hooks/useSceneTrack";

/** The crop's shift per nudge button press, in fractions of the window. */
const NUDGE = 0.05;

const clampOffset = (offset: number) =>
  Math.round(Math.min(1, Math.max(-1, offset)) * 100) / 100;

function formatOffset(offset: number): string {
  const percent = Math.round(offset * 100);
  return percent > 0 ? `+${percent}%` : `${percent}%`;
}

/**
 * The editor's Layout tab: how the scene at the playhead is framed
 * (SceneChooser), for auto fill a nudge of the crop window left or right
 * of where it follows the speaker (the clip's, for all its auto scenes),
 * the reframe controls (custom ratio, style), auto cut and auto zoom.
 */
export function LayoutPanel({
  clipId,
  edits,
  scenes,
  tracker,
  project,
}: {
  clipId: number;
  edits: ClipEdits;
  scenes: SceneEdits;
  tracker: SceneTracker;
  project?: Project;
}) {
  const gesture = useGesture();
  const { crop_offset: offset } = edits.look;
  const { current } = scenes;
  const nudgeable = current.layout === "fill" && current.mode === "auto";

  return (
    <>
      <PanelGroup title="Framing" collapsible>
        <SceneChooser scenes={scenes} tracker={tracker} />
        <ReframeControls
          clipId={clipId}
          edits={edits}
          project={project}
          tracking={current.mode === "track"}
        />
        <div className="flex flex-col gap-2">
          <PanelSlider
            label="Crop position"
            display={formatOffset(offset)}
            min={-100}
            max={100}
            step={1}
            value={Math.round(offset * 100)}
            disabled={!nudgeable}
            onChange={(percent) =>
              edits.setLook({ crop_offset: percent / 100 }, gesture.current())
            }
            onStart={gesture.begin}
          />
          <div className="flex items-center gap-1">
            <Button
              type="button"
              variant="outline"
              size="icon"
              aria-label="Nudge crop left"
              disabled={!nudgeable || offset <= -1}
              onClick={() =>
                edits.setLook({ crop_offset: clampOffset(offset - NUDGE) })
              }
            >
              <CaretLeftIcon aria-hidden />
            </Button>
            <Button
              type="button"
              variant="outline"
              size="icon"
              aria-label="Nudge crop right"
              disabled={!nudgeable || offset >= 1}
              onClick={() =>
                edits.setLook({ crop_offset: clampOffset(offset + NUDGE) })
              }
            >
              <CaretRightIcon aria-hidden />
            </Button>
            <Button
              type="button"
              variant="ghost"
              disabled={!nudgeable || offset === 0}
              onClick={() => edits.setLook({ crop_offset: 0 })}
            >
              Center on speaker
            </Button>
          </div>
          <p className="text-caption text-muted-foreground">
            {nudgeable
              ? "Moves the crop window away from the speaker; the video's edge stops it."
              : "Switch to Auto to move the crop."}
          </p>
        </div>
      </PanelGroup>
      <PanelGroup title="Auto edits" collapsible>
        <AutoCutToggle clipId={clipId} edits={edits} />
        <AutoZoomToggle clipId={clipId} edits={edits} />
      </PanelGroup>
      <p className="text-caption text-muted-foreground">
        The preview shows these changes once the clip is saved.
      </p>
    </>
  );
}
