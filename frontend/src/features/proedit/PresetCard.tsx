import { SkullIcon } from "@phosphor-icons/react";
import type { CSSProperties } from "react";
import type { ProEditPresetInfo } from "@/api/types";
import { cn } from "@/lib/utils";
import type { PresetId } from "./options";
import "./presetPreview.css";

const FALLBACK =
  "linear-gradient(140deg, #3b2a5c 0%, #c2410c 55%, #fbbf24 100%)";

/** The looping look of a preset over the poster (a gradient without one). */
export function PresetPreview({
  preset,
  posterUrl,
  className,
}: {
  preset: PresetId;
  posterUrl: string | null;
  className?: string;
}) {
  const media: CSSProperties = {
    backgroundImage: posterUrl ? `url("${posterUrl}")` : FALLBACK,
  };
  return (
    <div
      aria-hidden
      data-preset={preset}
      className={cn("pe-preview", `pe-${preset}`, className)}
    >
      <div className="pe-media" style={media} />
      {preset === "glitch" && (
        <div className="pe-media pe-ghost" style={media} />
      )}
      <div className="pe-fx" />
      {preset === "skull_moment" && <SkullIcon className="pe-skull" />}
    </div>
  );
}

interface PresetCardProps {
  preset: ProEditPresetInfo;
  posterUrl: string | null;
  checked: boolean;
  onPick: (preset: PresetId) => void;
}

/** A preset of the Pro Edit dialog: a radio with its looping preview, name,
 * description and BPM range. */
export function PresetCard({
  preset,
  posterUrl,
  checked,
  onPick,
}: PresetCardProps) {
  return (
    <label
      className={cn(
        "group flex cursor-pointer flex-col overflow-hidden rounded-xl border bg-field transition-colors has-[:focus-visible]:ring-3 has-[:focus-visible]:ring-ring/50",
        checked
          ? "border-primary ring-2 ring-primary/30"
          : "border-border hover:border-foreground/25",
      )}
    >
      <input
        type="radio"
        name="proedit-preset"
        value={preset.id}
        checked={checked}
        onChange={() => onPick(preset.id)}
        className="sr-only"
      />
      <PresetPreview
        preset={preset.id}
        posterUrl={posterUrl}
        className="aspect-[5/4] w-full"
      />
      <span className="flex flex-col gap-0.5 p-2.5">
        <span className="flex items-center justify-between gap-2">
          <span className="text-body font-semibold">{preset.name}</span>
          <span className="text-micro text-muted-foreground tabular-nums">
            {preset.bpm_min}–{preset.bpm_max} BPM
          </span>
        </span>
        <span className="line-clamp-2 text-caption text-muted-foreground">
          {preset.description}
        </span>
      </span>
    </label>
  );
}
