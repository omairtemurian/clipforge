import { FilmStripIcon } from "@phosphor-icons/react";
import type { StockClip } from "@/api/types";
import { Pill } from "@/components/ui/pill";
import { formatTimecode } from "@/lib/format";

interface StockResultProps {
  clip: StockClip;
  /** "Use" for a free spot, "Replace" when the spot has B-roll already. */
  action: "Use" | "Replace";
  disabled: boolean;
  onChoose: () => void;
}

/**
 * A stock video found for a spot: its thumbnail and length, the one
 * button that puts it on the clip, and the attribution and license it
 * comes with (always visible: the provider's terms ask for the credit).
 */
export function StockResult({
  clip,
  action,
  disabled,
  onChoose,
}: StockResultProps) {
  return (
    <li className="group flex flex-col gap-1.5">
      <button
        type="button"
        disabled={disabled}
        aria-label={`${action} with stock video by ${clip.creator} (${formatTimecode(clip.duration_s)})`}
        onClick={onChoose}
        className="relative flex aspect-video w-full cursor-pointer items-center justify-center overflow-hidden rounded-lg bg-muted ring-1 ring-border outline-none transition-[box-shadow] hover:ring-primary focus-visible:ring-3 focus-visible:ring-ring/50 disabled:cursor-not-allowed disabled:opacity-60"
      >
        {clip.preview_url ? (
          <img
            src={clip.preview_url}
            alt=""
            loading="lazy"
            className="size-full object-cover"
          />
        ) : (
          <FilmStripIcon className="size-6 text-muted-foreground" aria-hidden />
        )}
        <Pill tone="overlay" shape="tag" className="absolute right-1 bottom-1">
          {formatTimecode(clip.duration_s)}
        </Pill>
        <span className="absolute top-1 left-1 rounded-md bg-primary px-1.5 py-0.5 text-micro font-medium text-primary-foreground opacity-0 group-focus-within:opacity-100 group-hover:opacity-100">
          {action}
        </span>
      </button>
      <p className="text-micro text-muted-foreground">
        <a
          href={clip.page_url}
          target="_blank"
          rel="noreferrer"
          className="underline-offset-2 hover:underline"
        >
          {clip.attribution}
        </a>{" "}
        · {clip.license}
      </p>
    </li>
  );
}
