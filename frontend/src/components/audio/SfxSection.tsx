import { PlusIcon, SparkleIcon, TrashIcon } from "@phosphor-icons/react";
import { useState } from "react";
import { sfxFileUrl, useAutoSfx, useSfxPack } from "@/api/audio";
import type { Clip, SfxSound, TrackItem } from "@/api/types";
import { PreviewButton } from "@/components/audio/PreviewButton";
import { PanelSlider } from "@/components/editor/PanelSlider";
import { Button } from "@/components/ui/button";
import { PanelGroup } from "@/components/ui/panel";
import { Pill } from "@/components/ui/pill";
import { Skeleton } from "@/components/ui/skeleton";
import type { ClipEdits } from "@/hooks/useClipEdits";
import { useSoundPreview } from "@/hooks/useSoundPreview";
import { SFX_ITEMS_DEFAULT, SFX_ITEMS_MAX } from "@/lib/audio";
import { formatTimecode } from "@/lib/format";
import { removeItem } from "@/lib/layerItems";
import type { LayerName, LayerTracks } from "@/lib/layers";
import { mediaItem } from "@/lib/newLayerItems";

export interface SfxSectionProps {
  clip: Clip;
  edits: ClipEdits;
  /** A save or render is under way. */
  busy: boolean;
  /** The playhead in clip time (seconds after the cuts). */
  at: number;
  /** The clip time layer items must end by. */
  length: number;
  onChange: (name: LayerName, items: TrackItem[]) => void;
  onSelectItem: (id: string) => void;
}

interface SoundRowProps {
  sound: SfxSound;
  playing: boolean;
  canAdd: boolean;
  onPreview: () => void;
  onAdd: () => void;
}

/** A sound of the pack: listen, its tags and "Add at the playhead". */
function SoundRow({ sound, playing, canAdd, onPreview, onAdd }: SoundRowProps) {
  return (
    <li className="flex items-center gap-3 rounded-lg border border-border px-3 py-2">
      <PreviewButton
        name={sound.title}
        playing={playing}
        onToggle={onPreview}
      />
      <div className="flex min-w-0 flex-1 flex-col gap-1">
        <p className="truncate text-body" title={sound.title}>
          {sound.title}
        </p>
        <div className="flex flex-wrap gap-1">
          {sound.tags.map((tag) => (
            <Pill key={tag} shape="tag">
              {tag}
            </Pill>
          ))}
        </div>
      </div>
      <Button
        type="button"
        size="icon"
        variant="outline"
        aria-label={`Add ${sound.title} at the playhead`}
        title="Add at the playhead"
        disabled={!canAdd}
        onClick={onAdd}
        className="size-8 shrink-0"
      >
        <PlusIcon aria-hidden />
      </Button>
    </li>
  );
}

/**
 * The sound effects of the Audio panel: "Suggest sound effects" has the AI
 * place sounds of the bundled CC0 pack at cuts and key moments of the saved
 * clip (it waits for unsaved changes; the clip it answers replaces the
 * editor's), the placed sounds are listed with "Remove", and the pack's
 * sounds can be listened to and added at the playhead by hand.
 */
export function SfxSection({
  clip,
  edits,
  busy,
  at,
  length,
  onChange,
  onSelectItem,
}: SfxSectionProps) {
  const pack = useSfxPack();
  const suggest = useAutoSfx(clip.id);
  const preview = useSoundPreview();
  const [maxItems, setMaxItems] = useState(SFX_ITEMS_DEFAULT);
  const layers: LayerTracks = edits.layers;
  const sounds = pack.data ?? [];
  const locked = edits.dirty || busy || suggest.isPending;

  const run = async () => {
    try {
      edits.reset(await suggest.mutateAsync(maxItems));
    } catch {
      // apiFetch has shown the error
    }
  };
  const add = (sound: SfxSound) => {
    const item = mediaItem(
      layers,
      "sfx",
      {
        asset_id: sound.asset.id,
        kind: "audio",
        name: sound.title,
        duration: sound.duration,
      },
      at,
      length,
    );
    if (!item) return;
    onChange("sfx", [...layers.sfx, item]);
    onSelectItem(item.id);
  };
  const title = (item: TrackItem) =>
    sounds.find((sound) => sound.asset.id === item.asset_id)?.title ??
    "Sound effect";
  const placed = [...layers.sfx].sort((a, b) => a.start - b.start);

  return (
    <PanelGroup title="Sound effects">
      {edits.dirty && (
        <p role="status" className="text-caption text-muted-foreground">
          Suggestions wait until your changes are saved.
        </p>
      )}
      <PanelSlider
        label="Sounds to suggest"
        display={String(maxItems)}
        min={1}
        max={SFX_ITEMS_MAX}
        step={1}
        value={maxItems}
        onChange={setMaxItems}
      />
      <Button
        type="button"
        variant="secondary"
        disabled={locked}
        onClick={() => void run()}
      >
        <SparkleIcon aria-hidden />
        Suggest sound effects
      </Button>
      {suggest.isPending && (
        <p role="status" className="text-caption text-muted-foreground">
          Choosing sounds…
        </p>
      )}
      {placed.length > 0 && (
        <ul aria-label="Placed sound effects" className="flex flex-col gap-1.5">
          {placed.map((item) => (
            <li
              key={item.id}
              className="flex items-center justify-between gap-2 text-body"
            >
              <button
                type="button"
                onClick={() => onSelectItem(item.id)}
                className="min-w-0 flex-1 cursor-pointer truncate text-left hover:underline"
              >
                {title(item)}
              </button>
              <span className="shrink-0 text-micro text-muted-foreground tabular-nums">
                {formatTimecode(item.start)}
              </span>
              <Button
                type="button"
                size="icon"
                variant="ghost"
                aria-label={`Remove ${title(item)} at ${formatTimecode(item.start)}`}
                onClick={() => onChange("sfx", removeItem(layers.sfx, item.id))}
                className="size-7"
              >
                <TrashIcon aria-hidden />
              </Button>
            </li>
          ))}
        </ul>
      )}
      <p className="text-caption text-muted-foreground">
        Or add one from the pack at the playhead.
      </p>
      {pack.isPending ? (
        <Skeleton className="h-24 rounded-xl" />
      ) : (
        <ul aria-label="Sound effect pack" className="flex flex-col gap-2">
          {sounds.map((sound) => {
            const url = sfxFileUrl(sound.asset.id);
            return (
              <SoundRow
                key={sound.asset.id}
                sound={sound}
                playing={preview.playing === url}
                canAdd={length > 0}
                onPreview={() => preview.toggle(url)}
                onAdd={() => add(sound)}
              />
            );
          })}
        </ul>
      )}
    </PanelGroup>
  );
}
