import {
  CircleNotchIcon,
  FilmStripIcon,
  ImageIcon,
  MusicNotesIcon,
  PlusIcon,
  UploadSimpleIcon,
} from "@phosphor-icons/react";
import type { Icon as PhosphorIcon } from "@phosphor-icons/react";
import { useRef, useState } from "react";
import {
  mediaThumbnailUrl,
  useMediaLibrary,
  useUploadMedia,
} from "@/api/mediaLibrary";
import type { MediaItem, TrackItem } from "@/api/types";
import { ChoiceChips } from "@/components/settings/ChoiceChips";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Pill } from "@/components/ui/pill";
import { Skeleton } from "@/components/ui/skeleton";
import { formatDuration } from "@/lib/format";
import { LAYER_LABELS, type LayerName, type LayerTracks } from "@/lib/layers";
import {
  KIND_TRACKS,
  mediaDrag,
  mediaItem,
  mediaKind,
  mediaType,
  type MediaItemKind,
} from "@/lib/newLayerItems";
import { MEDIA_FRAME } from "@/lib/surfaces";
import { cn } from "@/lib/utils";

type Filter = "all" | MediaItemKind;

const FILTERS: { value: Filter; label: string }[] = [
  { value: "all", label: "All" },
  { value: "video", label: "Video" },
  { value: "image", label: "Images" },
  { value: "audio", label: "Audio" },
];

const KIND_ICONS: Record<MediaItemKind, PhosphorIcon> = {
  video: FilmStripIcon,
  image: ImageIcon,
  audio: MusicNotesIcon,
};

const ACCEPT = "image/*,video/*,audio/*";

export interface MediaLibraryProps {
  /** The clip's layer tracks as edited. */
  layers: LayerTracks;
  /** The playhead in clip time (seconds after the cuts). */
  at: number;
  /** The clip time layer items must end by. */
  length: number;
  /** New items of a layer track (a file added to it). */
  onAdd: (name: LayerName, items: TrackItem[]) => void;
  /** Select the added item on the timeline. */
  onSelectItem: (id: string) => void;
}

interface TileProps {
  media: MediaItem;
  onAdd: (media: MediaItem) => void;
  canAdd: boolean;
}

/** A library file: its thumbnail (dragged onto a track of the timeline),
 * name, length and an "add at the playhead" button. */
function MediaTile({ media, onAdd, canAdd }: TileProps) {
  const kind = mediaKind(media);
  const Icon = KIND_ICONS[kind];
  const track = LAYER_LABELS[KIND_TRACKS[kind][0]];
  return (
    <li className="group flex flex-col gap-1.5">
      <div
        draggable
        aria-label={`Drag ${media.name} onto the timeline`}
        title="Drag onto a track of the timeline"
        data-testid="media-tile"
        onDragStart={(event) => {
          event.dataTransfer.setData(
            mediaType(kind),
            JSON.stringify(mediaDrag(media)),
          );
          event.dataTransfer.effectAllowed = "copy";
        }}
        className={cn(MEDIA_FRAME, "aspect-video cursor-grab")}
      >
        {media.has_thumbnail ? (
          <img
            src={mediaThumbnailUrl(media.asset.id)}
            alt=""
            draggable={false}
            className="size-full object-cover"
          />
        ) : (
          <Icon
            aria-hidden
            className="absolute inset-0 m-auto size-6 text-muted-foreground"
          />
        )}
        <Pill tone="overlay" shape="tag" className="absolute top-1 left-1">
          <Icon aria-hidden className="size-3" />
        </Pill>
        {media.duration !== null && (
          <Pill
            tone="overlay"
            shape="tag"
            className="absolute right-1 bottom-1"
          >
            {formatDuration(media.duration)}
          </Pill>
        )}
        <Button
          type="button"
          size="icon"
          aria-label={`Add ${media.name} to the ${track} track`}
          title={`Add at the playhead (${track} track)`}
          disabled={!canAdd}
          onClick={() => onAdd(media)}
          className="absolute top-1 right-1 size-7 opacity-0 transition-opacity group-focus-within:opacity-100 group-hover:opacity-100"
        >
          <PlusIcon aria-hidden />
        </Button>
      </div>
      <p className="truncate text-caption" title={media.name}>
        {media.name}
      </p>
    </li>
  );
}

/**
 * The editor's Media panel (SPEC-v2 3.5): the media library's images,
 * logos, videos and audio as tiles, filtered by kind, and "Upload", which
 * adds files to the library. A tile drags onto a track of the timeline
 * that holds its kind (video and images: B-roll or Overlays; audio: Music,
 * SFX or Voiceover); its "+" adds it at the playhead to the first of them.
 */
export function MediaLibrary({
  layers,
  at,
  length,
  onAdd,
  onSelectItem,
}: MediaLibraryProps) {
  const library = useMediaLibrary();
  const upload = useUploadMedia();
  const input = useRef<HTMLInputElement>(null);
  const [filter, setFilter] = useState<Filter>("all");
  const files = (library.data ?? []).filter(
    (media) => filter === "all" || mediaKind(media) === filter,
  );

  const add = (media: MediaItem) => {
    const name = KIND_TRACKS[mediaKind(media)][0];
    const item = mediaItem(layers, name, mediaDrag(media), at, length);
    if (!item) return;
    onAdd(name, [...layers[name], item]);
    onSelectItem(item.id);
  };
  const choose = async (chosen: FileList | null) => {
    for (const file of Array.from(chosen ?? [])) {
      try {
        await upload.mutateAsync(file);
      } catch {
        // apiFetch has shown the error
      }
    }
    if (input.current) input.current.value = "";
  };
  const uploadButton = (
    <Button
      type="button"
      variant="outline"
      disabled={upload.isPending}
      onClick={() => input.current?.click()}
    >
      {upload.isPending ? (
        <CircleNotchIcon className="animate-spin" aria-hidden />
      ) : (
        <UploadSimpleIcon aria-hidden />
      )}
      Upload
    </Button>
  );

  return (
    <div className="flex flex-col gap-4">
      <input
        ref={input}
        type="file"
        multiple
        accept={ACCEPT}
        aria-label="Upload media files"
        className="hidden"
        onChange={(event) => void choose(event.target.files)}
      />
      {library.isPending ? (
        <div className="grid grid-cols-2 gap-3">
          {[0, 1, 2, 3].map((index) => (
            <Skeleton key={index} className="aspect-video rounded-xl" />
          ))}
        </div>
      ) : (library.data ?? []).length === 0 ? (
        <EmptyState
          icon={ImageIcon}
          title="No media yet"
          action={uploadButton}
          className="py-8"
        >
          Upload images, logos, videos or audio to put them on the timeline.
        </EmptyState>
      ) : (
        <>
          <div className="flex items-center justify-between gap-2">
            <p className="text-caption text-muted-foreground">
              Drag a file onto a track, or press + to add it at the playhead.
            </p>
            {uploadButton}
          </div>
          <ChoiceChips
            label="Media kind"
            options={FILTERS}
            value={filter}
            onChange={setFilter}
          />
          {files.length === 0 ? (
            <p className="text-caption text-muted-foreground">
              No files of this kind.
            </p>
          ) : (
            <ul aria-label="Media files" className="grid grid-cols-2 gap-3">
              {files.map((media) => (
                <MediaTile
                  key={media.asset.id}
                  media={media}
                  onAdd={add}
                  canAdd={length > 0}
                />
              ))}
            </ul>
          )}
        </>
      )}
    </div>
  );
}
