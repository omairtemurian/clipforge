import type { Clip } from "@/api/types";
import { MusicSection } from "@/components/audio/MusicSection";
import { SfxSection } from "@/components/audio/SfxSection";
import type { ClipEdits } from "@/hooks/useClipEdits";

export interface AudioPanelProps {
  clip: Clip;
  edits: ClipEdits;
  /** A save or render is under way. */
  busy: boolean;
  /** The playhead in clip time (seconds after the cuts). */
  at: number;
  /** The clip time layer items must end by. */
  length: number;
  /** The timeline's selected layer item, and selecting one. */
  selectedItem: string | null;
  onSelectItem: (id: string) => void;
}

/**
 * The editor's Audio panel (SPEC-v2 3.5): the music picker (bundled CC0
 * loops and uploads with their attribution; volume, fades and ducking),
 * the sound effects (AI suggestions from the bundled pack, or the pack's
 * sounds added by hand). The music and manual sound effects are edits of the
 * clip's tracks, saved with the other edits; the AI suggestions act on the
 * saved clip. Render the clip again to hear the changes.
 */
export function AudioPanel({
  clip,
  edits,
  busy,
  at,
  length,
  selectedItem,
  onSelectItem,
}: AudioPanelProps) {
  return (
    <>
      <MusicSection
        layers={edits.layers}
        length={length}
        onChange={edits.setLayer}
        selectedItem={selectedItem}
        onSelectItem={onSelectItem}
      />
      <SfxSection
        clip={clip}
        edits={edits}
        busy={busy}
        at={at}
        length={length}
        onChange={(name, items) => edits.setLayer(name, items)}
        onSelectItem={onSelectItem}
      />
      <p className="text-caption text-muted-foreground">
        Render the clip again to hear the changes.
      </p>
    </>
  );
}
