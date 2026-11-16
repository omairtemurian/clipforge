import { ClosedCaptioningIcon, FilmSlateIcon } from "@phosphor-icons/react";
import type { Icon as PhosphorIcon } from "@phosphor-icons/react";
import type { ProcessingSettings } from "@/api/types";
import { cn } from "@/lib/utils";

export type ClippingMode = ProcessingSettings["clipping"];

interface Tool {
  label: string;
  /** Spelled out after the label, so the tool is not picked by mistake. */
  detail?: string;
  mode: ClippingMode;
  icon: PhosphorIcon;
}

const TOOLS: Tool[] = [
  { label: "Long video to shorts", mode: "ai", icon: FilmSlateIcon },
  {
    label: "Captions only",
    detail: "(no clipping — whole video as one clip)",
    mode: "captions_only",
    icon: ClosedCaptioningIcon,
  },
];

interface ToolChipsProps {
  mode: ClippingMode;
  onModeChange: (mode: ClippingMode) => void;
}

/**
 * The row of rounded tool chips under the link input: AI clips, or the
 * whole video (or timeframe) as one captioned and reframed clip, labelled
 * as no clipping so it is not picked by mistake. The chosen
 * one is the clipping mode that the settings panel opens with.
 */
export function ToolChips({ mode, onModeChange }: ToolChipsProps) {
  return (
    <ul aria-label="Tools" className="mt-8 flex flex-wrap justify-center gap-2">
      {TOOLS.map(({ label, detail, mode: toolMode, icon: Icon }) => {
        const active = toolMode === mode;
        return (
          <li key={toolMode}>
            <button
              type="button"
              aria-pressed={active}
              onClick={() => onModeChange(toolMode)}
              className={cn(
                "flex h-9 items-center gap-2 rounded-full border px-4 text-body font-medium transition-colors outline-none focus-visible:ring-3 focus-visible:ring-ring/50",
                active
                  ? "border-primary/60 bg-primary/10 text-primary-ink"
                  : "border-border bg-card text-muted-foreground hover:border-foreground/20 hover:text-foreground",
              )}
            >
              <Icon className="size-4" aria-hidden />
              <span>
                {label}
                {detail && " "}
                {detail && (
                  <span className="font-normal opacity-80">{detail}</span>
                )}
              </span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}
