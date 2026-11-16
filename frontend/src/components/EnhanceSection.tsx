import { useState } from "react";
import { useSetEnhancement } from "@/api/clipCleanup";
import type { Clip } from "@/api/types";
import { EngineGate } from "@/components/EngineGate";
import { PanelSlider } from "@/components/editor/PanelSlider";
import { PanelGroup } from "@/components/ui/panel";
import type { ClipEdits } from "@/hooks/useClipEdits";
import { strengthLabel } from "@/lib/cleanup";

interface EnhanceSectionProps {
  clip: Clip;
  edits: ClipEdits;
  /** A save or render is under way. */
  busy: boolean;
}

/**
 * The speech enhancement of the clip: a strength slider (Off to 100%) that
 * the render applies to its sound. DeepFilterNet gives the cleanest result:
 * the engine gate says whether it is installed; without it the render uses
 * ffmpeg's noise filters. The setting acts on the saved clip, so it waits
 * for unsaved changes.
 */
export function EnhanceSection({ clip, edits, busy }: EnhanceSectionProps) {
  const set = useSetEnhancement(clip.id);
  const [dragged, setDragged] = useState<number | null>(null);
  const strength = dragged ?? clip.enhance;

  const commit = async (value: number) => {
    try {
      edits.reset(await set.mutateAsync({ strength: value }));
    } catch {
      // apiFetch has shown the error
    } finally {
      setDragged(null);
    }
  };

  return (
    <PanelGroup title="Speech enhancement">
      <PanelSlider
        label="Enhancement strength"
        display={strengthLabel(strength)}
        min={0}
        max={1}
        step={0.05}
        value={strength}
        disabled={edits.dirty || busy || set.isPending}
        onChange={setDragged}
        onCommit={(value) => void commit(value)}
      />
      <div className="flex flex-col gap-1 text-caption text-muted-foreground">
        <EngineGate engine="deepfilternet">
          <p role="status">DeepFilterNet is installed: the cleanest speech.</p>
        </EngineGate>
        <p>
          Without DeepFilterNet the render uses ffmpeg&apos;s noise filters.
          Render the clip again to hear it.
        </p>
      </div>
    </PanelGroup>
  );
}
