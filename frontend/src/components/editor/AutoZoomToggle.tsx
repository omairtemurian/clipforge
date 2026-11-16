import { useAutoZooms } from "@/api/clips";
import { ToggleRow } from "@/components/ui/toggle-row";
import type { ClipEdits } from "@/hooks/useClipEdits";
import { punchCount } from "@/lib/zoom";

/**
 * The Layout panel's auto zoom switch: on, the clip gets the punch-ins of
 * its span (GET /clips/{id}/auto-zooms) and the render zooms them; off, the
 * render does not zoom (the punch-ins are kept). It waits for the
 * punch-ins to load.
 */
export function AutoZoomToggle({
  clipId,
  edits,
}: {
  clipId: number;
  edits: ClipEdits;
}) {
  const autoZooms = useAutoZooms(clipId, edits.range, true);
  const { auto_zoom: on, zoom_keyframes: saved } = edits.look;
  const count = punchCount(autoZooms.data ?? []);
  const hint = autoZooms.isError
    ? "The punch-ins of this clip could not be found."
    : `Punch in on emphasis, new sentences and laughs (${count} in this clip).`;

  return (
    <ToggleRow
      label="Auto zoom"
      hint={hint}
      checked={on}
      disabled={!autoZooms.data}
      onCheckedChange={(next) =>
        edits.setLook({
          auto_zoom: next,
          zoom_keyframes: next ? (autoZooms.data ?? saved) : saved,
        })
      }
    />
  );
}
