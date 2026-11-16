import type { Clip } from "@/api/types";

/**
 * The clips in their order with each Pro Edit variant moved right after
 * its original (the variants oldest first), so the gallery shows them as
 * linked cards. A variant whose original is not in the list keeps its
 * place.
 */
export function groupVariants(clips: Clip[]): Clip[] {
  const ids = new Set(clips.map((clip) => clip.id));
  const variantsOf = new Map<number, Clip[]>();
  for (const clip of clips) {
    const parent = clip.parent_clip_id;
    if (clip.variant !== "pro_edit" || parent === null || !ids.has(parent)) {
      continue;
    }
    variantsOf.set(parent, [...(variantsOf.get(parent) ?? []), clip]);
  }
  const grouped: Clip[] = [];
  for (const clip of clips) {
    const parent = clip.parent_clip_id;
    if (clip.variant === "pro_edit" && parent !== null && ids.has(parent)) {
      continue;
    }
    grouped.push(clip);
    const variants = variantsOf.get(clip.id) ?? [];
    grouped.push(...variants.sort((a, b) => a.id - b.id));
  }
  return grouped;
}
