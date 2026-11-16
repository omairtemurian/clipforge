import { useAutoCuts } from "@/api/clips";
import { ToggleRow } from "@/components/ui/toggle-row";
import type { ClipEdits } from "@/hooks/useClipEdits";

/**
 * The Layout panel's auto cut switch: on, the silences of the clip's span
 * (GET /clips/{id}/auto-cuts) are cut; off, those cuts come back. It waits
 * for the silences to load.
 */
export function AutoCutToggle({
  clipId,
  edits,
}: {
  clipId: number;
  edits: ClipEdits;
}) {
  const autoCuts = useAutoCuts(clipId, edits.range, true);
  const on = edits.look.auto_cut;
  const count = autoCuts.data?.length ?? 0;
  const hint = autoCuts.isError
    ? "The silences of this clip could not be found."
    : `Jump cuts over the pauses between sentences (${count} in this clip).`;

  return (
    <ToggleRow
      label="Auto cut silences"
      hint={hint}
      checked={on}
      disabled={!autoCuts.data}
      onCheckedChange={(next) => edits.setAutoCut(next, autoCuts.data ?? [])}
    />
  );
}
