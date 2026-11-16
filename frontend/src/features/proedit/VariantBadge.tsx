import { MagicWandIcon } from "@phosphor-icons/react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { clipQuery } from "@/api/clips";
import type { Clip } from "@/api/types";
import { Pill } from "@/components/ui/pill";
import { cn } from "@/lib/utils";

/** The "Pro Edit" badge of a variant clip. */
export function ProEditBadge({
  overlay = false,
  className,
}: {
  /** Drawn over a preview (the card's corner). */
  overlay?: boolean;
  className?: string;
}) {
  return (
    <Pill
      tone={overlay ? "overlay" : "primary"}
      shape={overlay ? "tag" : "pill"}
      className={cn(overlay && "text-primary-ink", className)}
    >
      <MagicWandIcon className="size-3.5" aria-hidden />
      Pro Edit
    </Pill>
  );
}

/** The link from a variant to its original clip (its editor):
 * "Pro Edit of “Original title”". Nothing for an original clip. */
export function VariantOf({
  clip,
  className,
}: {
  clip: Clip;
  className?: string;
}) {
  const parentId = clip.parent_clip_id ?? 0;
  const parent = useQuery({
    ...clipQuery(parentId),
    enabled: clip.parent_clip_id !== null,
  });
  if (clip.variant !== "pro_edit" || clip.parent_clip_id === null) return null;
  const title = parent.data?.title ?? `clip ${parentId}`;
  return (
    <Link
      to={`/clips/${parentId}`}
      title={`Open the original: ${title}`}
      className={cn(
        "block truncate text-caption text-primary-ink underline-offset-4 hover:underline",
        className,
      )}
    >
      Pro Edit of “{title}”
    </Link>
  );
}
