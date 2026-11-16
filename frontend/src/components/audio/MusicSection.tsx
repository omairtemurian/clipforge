import { MusicNotesIcon, TrashIcon } from "@phosphor-icons/react";
import { musicFileUrl, useMusicLibrary } from "@/api/audio";
import type { MusicTrack, TrackItem } from "@/api/types";
import { PreviewButton } from "@/components/audio/PreviewButton";
import { PanelSlider } from "@/components/editor/PanelSlider";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { PanelGroup } from "@/components/ui/panel";
import { Pill } from "@/components/ui/pill";
import { Skeleton } from "@/components/ui/skeleton";
import { ToggleRow } from "@/components/ui/toggle-row";
import { useGesture } from "@/hooks/useGesture";
import { useSoundPreview } from "@/hooks/useSoundPreview";
import {
  chooseMusic,
  currentMusic,
  MUSIC_FADE_MAX,
  musicProps,
  patchProps,
  percent,
  seconds,
  VOLUME_MAX,
} from "@/lib/audio";
import { formatDuration } from "@/lib/format";
import { removeItem } from "@/lib/layerItems";
import type { LayerName, LayerTracks } from "@/lib/layers";
import { choiceClass } from "@/lib/surfaces";
import { cn } from "@/lib/utils";

export interface MusicSectionProps {
  layers: LayerTracks;
  /** The clip time layer items must end by. */
  length: number;
  /** New items of a layer track; changes of one gesture undo at once. */
  onChange: (name: LayerName, items: TrackItem[], gesture?: number) => void;
  selectedItem: string | null;
  onSelectItem: (id: string) => void;
}

interface TrackRowProps {
  track: MusicTrack;
  chosen: boolean;
  playing: boolean;
  canUse: boolean;
  onPreview: () => void;
  onUse: () => void;
}

/** A track of the music library: listen, its mood tags, its attribution
 * and license, and "Use". */
function TrackRow({
  track,
  chosen,
  playing,
  canUse,
  onPreview,
  onUse,
}: TrackRowProps) {
  const { attribution, license } = track.asset;
  const credit = attribution.includes(license)
    ? attribution
    : [attribution, license].filter(Boolean).join(" · ");
  return (
    <li className={cn(choiceClass(chosen), "flex items-start gap-3")}>
      <PreviewButton
        name={track.title}
        playing={playing}
        onToggle={onPreview}
      />
      <div className="flex min-w-0 flex-1 flex-col gap-1">
        <div className="flex items-baseline justify-between gap-2">
          <p className="truncate text-body font-medium" title={track.title}>
            {track.title}
          </p>
          {track.duration !== null && (
            <span className="shrink-0 text-micro text-muted-foreground tabular-nums">
              {formatDuration(track.duration)}
            </span>
          )}
        </div>
        {track.tags.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {track.tags.map((tag) => (
              <Pill key={tag} shape="tag">
                {tag}
              </Pill>
            ))}
          </div>
        )}
        <p className="text-micro text-muted-foreground">{credit}</p>
      </div>
      <Button
        type="button"
        size="sm"
        variant={chosen ? "secondary" : "outline"}
        aria-label={`Use ${track.title} as music`}
        aria-pressed={chosen}
        disabled={!canUse || chosen}
        onClick={onUse}
      >
        {chosen ? "In use" : "Use"}
      </Button>
    </li>
  );
}

/** The sliders and switch of the clip's music item: volume, fades and
 * ducking under the speech, and "Remove music". */
function MusicControls({
  item,
  onChange,
  onRemove,
}: {
  item: TrackItem;
  onChange: (
    changes: Partial<ReturnType<typeof musicProps>>,
    g?: number,
  ) => void;
  onRemove: () => void;
}) {
  const gesture = useGesture();
  const props = musicProps(item);
  const slider = (
    label: string,
    key: "volume" | "fade_in" | "fade_out",
    max: number,
    step: number,
    display: (value: number) => string,
  ) => (
    <PanelSlider
      label={label}
      display={display(props[key])}
      min={0}
      max={max}
      step={step}
      value={props[key]}
      onStart={gesture.begin}
      onChange={(value) => onChange({ [key]: value }, gesture.current())}
    />
  );
  return (
    <>
      {slider("Music volume", "volume", VOLUME_MAX, 0.05, percent)}
      {slider("Fade in", "fade_in", MUSIC_FADE_MAX, 0.5, seconds)}
      {slider("Fade out", "fade_out", MUSIC_FADE_MAX, 0.5, seconds)}
      <ToggleRow
        label="Duck under speech"
        hint="Lowers the music while someone talks"
        checked={props.duck}
        onCheckedChange={(duck) => onChange({ duck })}
      />
      <Button type="button" variant="outline" onClick={onRemove}>
        <TrashIcon aria-hidden />
        Remove music
      </Button>
    </>
  );
}

/**
 * The music of the Audio panel: the library's tracks (the bundled CC0
 * loops, then uploads) to listen to and "Use" as the clip's music, with
 * each track's attribution and license; the music then has volume, fades
 * and ducking settings. The music plays over the whole clip (it loops). All
 * edits go to the music track like the timeline's, saved with the rest.
 */
export function MusicSection({
  layers,
  length,
  onChange,
  selectedItem,
  onSelectItem,
}: MusicSectionProps) {
  const library = useMusicLibrary();
  const preview = useSoundPreview();
  const current = currentMusic(layers, selectedItem);

  const use = (track: MusicTrack) => {
    const items = chooseMusic(layers, current, track.asset.id, length);
    if (!items) return;
    onChange("music", items);
    const picked = current ?? items[items.length - 1];
    onSelectItem(picked.id);
  };

  return (
    <PanelGroup title="Music">
      {library.isPending ? (
        <Skeleton className="h-24 rounded-xl" />
      ) : (library.data ?? []).length === 0 ? (
        <EmptyState icon={MusicNotesIcon} title="No music" className="py-6">
          Upload a music file in the Media panel to use it here.
        </EmptyState>
      ) : (
        <ul aria-label="Music tracks" className="flex flex-col gap-2">
          {(library.data ?? []).map((track) => {
            const url = musicFileUrl(track.asset.id);
            return (
              <TrackRow
                key={track.asset.id}
                track={track}
                chosen={current?.asset_id === track.asset.id}
                playing={preview.playing === url}
                canUse={length > 0}
                onPreview={() => preview.toggle(url)}
                onUse={() => use(track)}
              />
            );
          })}
        </ul>
      )}
      {current && (
        <MusicControls
          key={current.id}
          item={current}
          onChange={(changes, gesture) =>
            onChange(
              "music",
              patchProps(layers.music, current.id, changes),
              gesture,
            )
          }
          onRemove={() =>
            onChange("music", removeItem(layers.music, current.id))
          }
        />
      )}
    </PanelGroup>
  );
}
