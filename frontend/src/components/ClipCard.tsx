import {
  CircleNotchIcon,
  DownloadSimpleIcon,
  ScissorsIcon,
  TrashIcon,
} from "@phosphor-icons/react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { apiUrl } from "@/api/client";
import type { Clip } from "@/api/types";
import { ScoreBadge } from "@/components/ScoreBadge";
import { PostButton } from "@/components/posts/PostButton";
import {
  ProEditBadge,
  ProEditButton,
  VariantOf,
  VariantProgress,
  proEditPath,
} from "@/features/proedit";
import { Pill } from "@/components/ui/pill";
import { MEDIA_FRAME } from "@/lib/surfaces";
import { clipLength, isEdited } from "@/lib/clips";
import { formatDuration } from "@/lib/format";

const LAYOUT_LABEL: Record<Clip["layout"], string> = {
  fill: "Fill",
  fit: "Fit",
  split: "Split",
  grid: "Grid",
  pip: "Picture in picture",
  screenshare: "Screenshare + facecam",
  gameplay: "Gameplay + facecam",
  square_blur: "Square",
};

const ACTION =
  "inline-flex size-8 items-center justify-center rounded-lg text-muted-foreground outline-none transition-colors hover:bg-muted hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/50 disabled:pointer-events-none disabled:opacity-50";

/** Where a card's Edit goes: a variant's to its original's Pro Edit page
 * (the v1 editor would render over the variant), a clip's to its editor. */
function editPath(clip: Clip): string {
  return clip.variant === "pro_edit" && clip.parent_clip_id !== null
    ? proEditPath(clip.parent_clip_id, clip.id)
    : `/clips/${clip.id}`;
}

interface ClipCardProps {
  clip: Clip;
  /** The project's thumbnail, shown until the preview plays. */
  posterUrl: string | null;
  /** A render job is waiting for this clip or working on it. */
  rendering: boolean;
  onRender: (clip: Clip) => void;
  onRemove: (clip: Clip) => void;
}

/** The 9:16 preview of a clip; it plays muted, looping, while hovered. */
function Preview({
  clip,
  posterUrl,
}: Pick<ClipCardProps, "clip" | "posterUrl">) {
  const [active, setActive] = useState(false);
  const [broken, setBroken] = useState(false);

  return (
    <div
      className={`${MEDIA_FRAME} aspect-[9/16]`}
      onMouseEnter={() => setActive(true)}
      onMouseLeave={() => setActive(false)}
    >
      {posterUrl && (
        <img
          src={posterUrl}
          alt=""
          loading="lazy"
          className="absolute inset-0 size-full object-cover"
        />
      )}
      {active && !broken && (
        <video
          src={apiUrl(`/clips/${clip.id}/preview`)}
          aria-label={`Preview of ${clip.title}`}
          autoPlay
          muted
          loop
          playsInline
          onError={() => setBroken(true)}
          className="absolute inset-0 size-full object-cover"
        />
      )}
      <Pill tone="overlay" shape="tag" className="absolute bottom-2 left-2">
        {LAYOUT_LABEL[clip.layout]}
      </Pill>
      <Pill
        tone="overlay"
        shape="tag"
        aria-label="Duration"
        className="absolute right-2 bottom-2"
      >
        {formatDuration(clipLength(clip))}
      </Pill>
      {clip.variant === "pro_edit" && (
        <ProEditBadge overlay className="absolute top-2 left-2" />
      )}
      <VariantProgress clip={clip} />
      {isEdited(clip) && (
        <Pill tone="overlay" shape="tag" className="absolute top-2 right-2">
          Edited
        </Pill>
      )}
    </div>
  );
}

function DownloadAction({
  clip,
  rendering,
  onRender,
}: Pick<ClipCardProps, "clip" | "rendering" | "onRender">) {
  if (rendering) {
    return (
      <button type="button" disabled aria-label="Rendering" className={ACTION}>
        <CircleNotchIcon className="size-4 animate-spin" aria-hidden />
      </button>
    );
  }
  if (clip.status === "rendered") {
    return (
      <a
        href={apiUrl(`/clips/${clip.id}/download`)}
        aria-label="Download clip"
        title="Download"
        className={ACTION}
      >
        <DownloadSimpleIcon className="size-4" aria-hidden />
      </a>
    );
  }
  return (
    <button
      type="button"
      aria-label="Render clip"
      title="Render, then download"
      onClick={() => onRender(clip)}
      className={ACTION}
    >
      <DownloadSimpleIcon className="size-4" aria-hidden />
    </button>
  );
}

/**
 * A clip of the gallery: the preview, its score (click for the breakdown),
 * download, post, edit and remove buttons, the title and a two-line snippet.
 */
export function ClipCard({
  clip,
  posterUrl,
  rendering,
  onRender,
  onRemove,
}: ClipCardProps) {
  return (
    <article aria-label={clip.title} className="group min-w-0">
      <Preview clip={clip} posterUrl={posterUrl} />
      <div className="mt-2 flex items-center gap-1">
        <ScoreBadge clip={clip} />
        <span className="flex-1" />
        <DownloadAction clip={clip} rendering={rendering} onRender={onRender} />
        <PostButton clip={clip} compact />
        <ProEditButton clip={clip} look="icon" className={ACTION} />
        <Link
          to={editPath(clip)}
          aria-label="Edit clip"
          title="Edit"
          className={ACTION}
        >
          <ScissorsIcon className="size-4" aria-hidden />
        </Link>
        <button
          type="button"
          aria-label="Remove clip"
          title="Remove"
          disabled={rendering}
          onClick={() => onRemove(clip)}
          className={ACTION}
        >
          <TrashIcon className="size-4" aria-hidden />
        </button>
      </div>
      <h3
        className="mt-1 line-clamp-2 text-body font-semibold"
        title={clip.title}
      >
        {clip.title}
      </h3>
      <VariantOf clip={clip} className="mt-0.5" />
      <p className="mt-1 line-clamp-2 text-caption text-muted-foreground">
        {clip.description}
      </p>
    </article>
  );
}
