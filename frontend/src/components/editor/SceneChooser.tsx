import { CircleNotchIcon, CrosshairIcon } from "@phosphor-icons/react";
import { LayoutPicker } from "@/components/LayoutPicker";
import { Field } from "@/components/settings/Field";
import { Button } from "@/components/ui/button";
import type { SceneEdits } from "@/hooks/useSceneEdits";
import type { SceneTracker } from "@/hooks/useSceneTrack";
import { formatTimecode } from "@/lib/format";
import { sceneChoice } from "@/lib/scenes";

/**
 * How the scene at the playhead is framed (LayoutPicker): auto (follows
 * the speaker), track (follows the subject picked on the video, with a
 * button to pick another), fixed (at the crop tool's keyframes) or one of
 * the layouts; with more than one scene, titled with the scene and with
 * "Apply to all scenes".
 */
export function SceneChooser({
  scenes,
  tracker,
}: {
  scenes: SceneEdits;
  tracker: SceneTracker;
}) {
  const { current, index } = scenes;
  const count = scenes.scenes.length;
  const choice = sceneChoice(current);
  const title =
    count > 1
      ? `Scene ${index + 1} of ${count} · ${formatTimecode(current.start)} – ${formatTimecode(current.end)}`
      : "Layout";

  return (
    <Field label={title}>
      <LayoutPicker value={choice} onChange={scenes.choose} />
      {choice === "track" && (
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="self-start"
          disabled={tracker.tracking || tracker.picking}
          onClick={() => tracker.setPicking(true)}
        >
          {tracker.tracking ? (
            <CircleNotchIcon className="animate-spin" aria-hidden />
          ) : (
            <CrosshairIcon aria-hidden />
          )}
          {tracker.tracking
            ? "Tracking…"
            : current.crop_keyframes.length > 0
              ? "Pick another subject"
              : "Pick the subject"}
        </Button>
      )}
      {count > 1 && (
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="self-start"
          onClick={scenes.applyToAll}
        >
          Apply to all scenes
        </Button>
      )}
    </Field>
  );
}
