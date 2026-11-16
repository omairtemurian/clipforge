import { apiUrl } from "@/api/client";
import type { Clip } from "@/api/types";

/** A short hash (FNV-1a, base 36) of text. */
function hash(text: string): string {
  let value = 0x811c9dc5;
  for (let k = 0; k < text.length; k++) {
    value ^= text.charCodeAt(k);
    value = Math.imul(value, 0x01000193);
  }
  return (value >>> 0).toString(36);
}

/** A short version key of the clip's saved edits: all of the clip but its
 * render status and output. */
export function editsVersion(clip: Clip): string {
  return hash(JSON.stringify({ ...clip, status: null, output_path: null }));
}

/**
 * The URL of the clip's 540p preview (GET /clips/{id}/preview), versioned
 * by the saved edits (editsVersion), so the player loads it again after
 * each save.
 */
export function previewUrl(clip: Clip): string {
  return apiUrl(`/clips/${clip.id}/preview?v=${editsVersion(clip)}`);
}
