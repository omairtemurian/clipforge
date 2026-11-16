/**
 * The AI copy in the "Schedule post" form: what a PostCopy of the API
 * puts in a platform's fields, and the current text it is rewritten from.
 */
import type { PostCopy } from "@/api/types";
import { formatHashtags, parseHashtags } from "@/lib/clipText";
import type { PostFields } from "@/lib/postForm";

/** The fields with the copy's title, caption and hashtags; the privacy is
 * the user's and stays. */
export function withCopy(fields: PostFields, copy: PostCopy): PostFields {
  return {
    ...fields,
    title: copy.title,
    caption: copy.caption,
    hashtags: formatHashtags(copy.hashtags),
  };
}

/** The text of the fields, for the API to rewrite. */
export function currentCopy(fields: PostFields): PostCopy {
  return {
    title: fields.title.trim(),
    caption: fields.caption,
    hashtags: parseHashtags(fields.hashtags),
  };
}

/** The seconds of the clip's rendered video: its segments less the cuts. */
export function clipSeconds(clip: {
  segments: readonly (readonly [number, number])[];
  cut_ranges: readonly (readonly [number, number])[];
}): number {
  const span = (list: readonly (readonly [number, number])[]) =>
    list.reduce((sum, [from, to]) => sum + Math.max(0, to - from), 0);
  return Math.max(0, span(clip.segments) - span(clip.cut_ranges));
}
